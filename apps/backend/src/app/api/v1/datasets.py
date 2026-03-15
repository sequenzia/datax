"""Dataset API endpoints.

Provides file upload, CRUD operations, and data preview with pagination
and sorting for uploaded datasets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import duckdb
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.background import BackgroundTask

from app.dependencies import get_db, get_duckdb_manager, get_session_factory, get_storage_path
from app.errors import AppError
from app.logging import get_logger
from app.models.dataset import DatasetStatus
from app.models.orm import DataProfile, Dataset, SchemaMetadata
from app.services.duckdb_manager import DuckDBManager, sanitize_table_name
from app.services.file_upload import (
    UPLOAD_CHUNK_SIZE,
    ensure_storage_dir,
    generate_unique_filename,
    sanitize_filename,
    validate_file_format,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_uuid(value: str, field_name: str = "id") -> UUID:
    """Validate and parse a UUID string, raising 400 on invalid format."""
    if not _UUID_PATTERN.match(value):
        raise AppError(
            code="INVALID_UUID",
            message=f"Invalid UUID format for {field_name}: {value}",
            status_code=400,
        )
    return UUID(value)


# ---------------------------------------------------------------------------
# Upload Endpoint
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=202)
async def upload_dataset(
    file: UploadFile,
    name: str | None = Form(default=None),
    storage_path: Path = Depends(get_storage_path),
    db: Session = Depends(get_db),
    duckdb_mgr: DuckDBManager = Depends(get_duckdb_manager),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> JSONResponse:
    """Upload a data file for analysis.

    Accepts CSV, Excel (.xlsx, .xls), Parquet, and JSON files via
    multipart/form-data. The file is streamed to disk in chunks to
    avoid loading the entire file into memory. A Dataset record is
    created immediately and DuckDB registration is triggered as a
    background task.

    Returns 202 Accepted with the dataset metadata.
    """
    original_filename = file.filename or "unnamed_file"

    # Validate file format
    try:
        file_format = validate_file_format(original_filename)
    except ValueError as exc:
        raise AppError(
            code="UNSUPPORTED_FORMAT",
            message=str(exc),
            status_code=400,
        ) from exc

    # Ensure storage directory exists and is writable
    try:
        ensure_storage_dir(storage_path)
    except OSError as exc:
        logger.error("storage_not_writable", path=str(storage_path), error=str(exc))
        raise AppError(
            code="STORAGE_ERROR",
            message="File storage is not available. Please contact an administrator.",
            status_code=500,
        ) from exc

    # Sanitize filename and generate unique storage name
    sanitized = sanitize_filename(original_filename)
    unique_name = generate_unique_filename(sanitized, storage_path)
    dest_path = storage_path / unique_name

    # Stream file to disk in chunks
    file_size = 0
    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                file_size += len(chunk)
    except OSError as exc:
        # Clean up partial file
        dest_path.unlink(missing_ok=True)
        logger.error("upload_write_failed", path=str(dest_path), error=str(exc))
        raise AppError(
            code="UPLOAD_FAILED",
            message="Failed to write uploaded file to storage.",
            status_code=500,
        ) from exc

    # Reject empty files
    if file_size == 0:
        dest_path.unlink(missing_ok=True)
        raise AppError(
            code="EMPTY_FILE",
            message="Uploaded file is empty. Please upload a file with data.",
            status_code=400,
        )

    # Generate display name and unique DuckDB table name
    display_name = name if name else Path(original_filename).stem
    duckdb_table = sanitize_table_name(original_filename)

    # Ensure table name uniqueness by appending UUID suffix
    duckdb_table = f"{duckdb_table}_{dest_path.stem.split('_')[-1]}"

    # Create Dataset record — commit immediately so the background task
    # (which uses a separate session) can see the row.
    dataset = Dataset(
        name=display_name,
        file_path=str(dest_path),
        file_format=file_format,
        duckdb_table_name=duckdb_table,
        status=DatasetStatus.PROCESSING.value,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    dataset_id = str(dataset.id)
    created_at = dataset.created_at.isoformat() if dataset.created_at else None

    logger.info(
        "dataset_upload_started",
        dataset_id=dataset_id,
        name=display_name,
        file_format=file_format,
        file_size_bytes=file_size,
        duckdb_table=duckdb_table,
    )

    response_body = {
        "id": dataset_id,
        "name": display_name,
        "file_format": file_format,
        "status": DatasetStatus.PROCESSING.value,
        "created_at": created_at,
    }

    return JSONResponse(
        content=response_body,
        status_code=202,
        background=BackgroundTask(
            _register_in_duckdb,
            dataset_id=dataset.id,
            file_path=dest_path,
            file_format=file_format,
            duckdb_table=duckdb_table,
            duckdb_mgr=duckdb_mgr,
            session_factory=session_factory,
        ),
    )


def _register_in_duckdb(
    dataset_id: UUID,
    file_path: Path,
    file_format: str,
    duckdb_table: str,
    duckdb_mgr: DuckDBManager,
    session_factory: sessionmaker[Session],
) -> None:
    """Background task: register the uploaded file in DuckDB and update the Dataset.

    This runs after the 202 response is sent. It registers the file in DuckDB,
    extracts the schema, and updates the Dataset record status to 'ready' or 'error'.
    """
    result = duckdb_mgr.register_file(file_path, duckdb_table, file_format)

    # Create a new session for background work since the request session is closed
    session = session_factory()

    try:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            logger.error("bg_register_dataset_missing", dataset_id=str(dataset_id))
            return

        if result.is_success:
            dataset.status = DatasetStatus.READY.value
            dataset.row_count = result.row_count

            # Persist schema metadata
            for col in result.columns:
                schema_row = SchemaMetadata(
                    source_id=dataset_id,
                    source_type="dataset",
                    table_name=duckdb_table,
                    column_name=col.column_name,
                    data_type=col.data_type,
                    is_nullable=col.is_nullable,
                    is_primary_key=col.is_primary_key,
                )
                session.add(schema_row)

            # Run data profiling: SUMMARIZE + sample values
            summarize_results = duckdb_mgr.summarize_table(duckdb_table)
            sample_values = duckdb_mgr.get_sample_values(duckdb_table)

            # Store combined profile in Dataset.data_stats
            dataset.data_stats = {
                "summarize": summarize_results,
                "sample_values": sample_values,
            }

            # Store in DataProfile for dedicated profiling access
            profile = DataProfile(
                dataset_id=dataset_id,
                summarize_results=summarize_results,
                sample_values=sample_values,
            )
            session.add(profile)

            logger.info(
                "dataset_registration_complete",
                dataset_id=str(dataset_id),
                row_count=result.row_count,
                column_count=len(result.columns),
                profile_columns=len(summarize_results),
            )
        else:
            dataset.status = DatasetStatus.ERROR.value
            logger.error(
                "dataset_registration_failed",
                dataset_id=str(dataset_id),
                error=result.error_message,
            )

        session.commit()
    except Exception:
        session.rollback()
        logger.error(
            "bg_register_db_error",
            dataset_id=str(dataset_id),
            exc_info=True,
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.get("")
def list_datasets(db: Session = Depends(get_db)) -> dict:
    """List all datasets sorted by created_at descending."""
    stmt = select(Dataset).order_by(Dataset.created_at.desc())
    datasets = list(db.execute(stmt).scalars().all())

    return {
        "datasets": [
            {
                "id": str(ds.id),
                "name": ds.name,
                "file_format": ds.file_format,
                "row_count": ds.row_count,
                "status": ds.status,
                "created_at": ds.created_at.isoformat() if ds.created_at else None,
                "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
            }
            for ds in datasets
        ],
    }


@router.get("/{dataset_id}")
def get_dataset(dataset_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a dataset with its schema metadata."""
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dataset {dataset_id} not found",
            status_code=404,
        )

    # Fetch schema metadata for this dataset
    schema_stmt = (
        select(SchemaMetadata)
        .where(SchemaMetadata.source_id == dataset_id)
        .where(SchemaMetadata.source_type == "dataset")
    )
    schema_rows = list(db.execute(schema_stmt).scalars().all())

    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "file_format": dataset.file_format,
        "row_count": dataset.row_count,
        "duckdb_table_name": dataset.duckdb_table_name,
        "status": dataset.status,
        "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
        "schema": [
            {
                "column_name": col.column_name,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
            }
            for col in schema_rows
        ],
    }


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: UUID,
    db: Session = Depends(get_db),
    duckdb_mgr: DuckDBManager = Depends(get_duckdb_manager),
) -> Response:
    """Delete a dataset, its file, DuckDB table, and DB records.

    Cleans up in order: DuckDB table, file on disk, schema metadata, dataset record.
    File deletion failures are logged but do not prevent DB cleanup.
    """
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dataset {dataset_id} not found",
            status_code=404,
        )

    if dataset.status == DatasetStatus.PROCESSING.value:
        raise AppError(
            code="DATASET_PROCESSING",
            message=f"Dataset {dataset_id} is currently being processed and cannot be deleted",
            status_code=409,
        )

    # 1. Unregister from DuckDB
    duckdb_mgr.unregister_table(dataset.duckdb_table_name)

    # 2. Delete file on disk (best-effort: log errors but continue)
    file_path = Path(dataset.file_path)
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info("dataset_file_deleted", file_path=str(file_path))
    except OSError as exc:
        logger.warning(
            "dataset_file_delete_failed",
            file_path=str(file_path),
            error=str(exc),
        )

    # 3. Delete schema metadata
    schema_stmt = (
        select(SchemaMetadata)
        .where(SchemaMetadata.source_id == dataset_id)
        .where(SchemaMetadata.source_type == "dataset")
    )
    schema_rows = list(db.execute(schema_stmt).scalars().all())
    for row in schema_rows:
        db.delete(row)

    # 4. Delete dataset record
    db.delete(dataset)
    db.flush()

    logger.info("dataset_deleted", dataset_id=str(dataset_id))

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Profile Endpoint
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/profile")
def get_dataset_profile(
    dataset_id: UUID,
    db: Session = Depends(get_db),
    duckdb_mgr: DuckDBManager = Depends(get_duckdb_manager),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> dict:
    """Return stored profiling data for a dataset.

    If the dataset exists but has not been profiled yet, triggers on-demand
    profiling (SUMMARIZE + sample extraction) and stores the results before
    returning them.
    """
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dataset {dataset_id} not found",
            status_code=404,
        )

    # Look for existing profile
    profile = db.query(DataProfile).filter(
        DataProfile.dataset_id == dataset_id
    ).first()

    if profile is not None:
        return {
            "dataset_id": str(dataset_id),
            "summarize_results": profile.summarize_results or [],
            "sample_values": profile.sample_values or {},
            "profiled_at": profile.profiled_at.isoformat() if profile.profiled_at else None,
        }

    # Dataset not yet profiled — trigger on-demand profiling
    if dataset.status != DatasetStatus.READY.value:
        raise AppError(
            code="DATASET_NOT_READY",
            message=f"Dataset is not ready for profiling. Current status: {dataset.status}",
            status_code=409,
        )

    summarize_results = duckdb_mgr.summarize_table(dataset.duckdb_table_name)
    sample_values = duckdb_mgr.get_sample_values(dataset.duckdb_table_name)

    # Store in DataProfile
    new_profile = DataProfile(
        dataset_id=dataset_id,
        summarize_results=summarize_results,
        sample_values=sample_values,
    )
    db.add(new_profile)

    # Also update Dataset.data_stats for consistency
    dataset.data_stats = {
        "summarize": summarize_results,
        "sample_values": sample_values,
    }

    db.flush()
    db.refresh(new_profile)

    return {
        "dataset_id": str(dataset_id),
        "summarize_results": new_profile.summarize_results or [],
        "sample_values": new_profile.sample_values or {},
        "profiled_at": new_profile.profiled_at.isoformat() if new_profile.profiled_at else None,
    }


# ---------------------------------------------------------------------------
# Preview Endpoint
# ---------------------------------------------------------------------------


@router.get("/{dataset_id}/preview")
def get_dataset_preview(
    dataset_id: UUID,
    offset: int = Query(default=0, ge=0, description="Row offset for pagination"),
    limit: int = Query(default=100, ge=0, description="Max rows to return"),
    sort_by: str | None = Query(default=None, description="Column name to sort by"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction"),
    db: Session = Depends(get_db),
    duckdb_mgr: DuckDBManager = Depends(get_duckdb_manager),
) -> dict[str, Any]:
    """Return a paginated, sortable preview of a dataset's data.

    Queries the DuckDB virtual table associated with the dataset and returns
    column names and row data as arrays for efficiency.
    """
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dataset {dataset_id} not found",
            status_code=404,
        )

    if dataset.status != DatasetStatus.READY.value:
        raise AppError(
            code="DATASET_NOT_READY",
            message=f"Dataset is not ready for preview. Current status: {dataset.status}",
            status_code=409,
        )

    return _build_preview(duckdb_mgr, dataset, offset, limit, sort_by, sort_order)


def _build_preview(
    duckdb_mgr: DuckDBManager,
    dataset: Dataset,
    offset: int,
    limit: int,
    sort_by: str | None,
    sort_order: str,
) -> dict[str, Any]:
    """Build the preview response by querying DuckDB."""
    table_name = dataset.duckdb_table_name

    if not duckdb_mgr.is_table_registered(table_name):
        raise HTTPException(
            status_code=500,
            detail=f"DuckDB table '{table_name}' is not registered",
        )

    try:
        columns = _get_column_names(duckdb_mgr, table_name)
    except duckdb.Error as exc:
        logger.error("preview_schema_error", table_name=table_name, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read table schema: {exc}",
        ) from exc

    if sort_by is not None and sort_by not in columns:
        raise HTTPException(
            status_code=400,
            detail=f"Column '{sort_by}' does not exist. Available columns: {columns}",
        )

    try:
        total_rows = _get_total_rows(duckdb_mgr, table_name)
    except duckdb.Error as exc:
        logger.error("preview_count_error", table_name=table_name, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to count rows: {exc}",
        ) from exc

    try:
        rows = _fetch_rows(duckdb_mgr, table_name, offset, limit, sort_by, sort_order)
    except duckdb.Error as exc:
        logger.error("preview_query_error", table_name=table_name, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch preview data: {exc}",
        ) from exc

    return {
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
        "offset": offset,
        "limit": limit,
    }


def _get_column_names(duckdb_mgr: DuckDBManager, table_name: str) -> list[str]:
    """Get column names from a DuckDB table."""
    result = duckdb_mgr._conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
    return [desc[0] for desc in result.description]


def _get_total_rows(duckdb_mgr: DuckDBManager, table_name: str) -> int:
    """Get total row count for a table."""
    result = duckdb_mgr._conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return result.fetchone()[0]  # type: ignore[index]


def _fetch_rows(
    duckdb_mgr: DuckDBManager,
    table_name: str,
    offset: int,
    limit: int,
    sort_by: str | None,
    sort_order: str,
) -> list[list[Any]]:
    """Fetch paginated rows from a DuckDB table as arrays."""
    sql = f"SELECT * FROM {table_name}"

    if sort_by is not None:
        direction = "ASC" if sort_order == "asc" else "DESC"
        sql += f' ORDER BY "{sort_by}" {direction}'

    sql += f" LIMIT {limit} OFFSET {offset}"

    result = duckdb_mgr._conn.execute(sql)
    rows = result.fetchall()

    return [_serialize_row(row) for row in rows]


def _serialize_row(row: tuple) -> list[Any]:
    """Convert a DuckDB row tuple to a JSON-serializable list."""
    result = []
    for val in row:
        if val is None:
            result.append(None)
        elif isinstance(val, (int, float, str, bool)):
            result.append(val)
        else:
            result.append(str(val))
    return result
