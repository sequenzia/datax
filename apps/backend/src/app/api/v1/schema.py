"""Unified schema registry API endpoint.

Provides a single endpoint that aggregates SchemaMetadata from both datasets
and connections, grouping by source -> table -> columns.  Used by the AI
agent, SQL autocomplete, and the schema browser UI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import connections as connections_module
from app.dependencies import get_db
from app.logging import get_logger
from app.models.orm import Dataset, SchemaMetadata

logger = get_logger(__name__)

router = APIRouter(tags=["schema"])


def _build_column_entry(row: SchemaMetadata) -> dict[str, Any]:
    """Build a single column dict from a SchemaMetadata row."""
    entry: dict[str, Any] = {
        "name": row.column_name,
        "type": row.data_type,
        "nullable": row.is_nullable,
        "is_primary_key": row.is_primary_key,
    }
    if row.foreign_key_ref is not None:
        entry["foreign_key_ref"] = row.foreign_key_ref
    return entry


def _build_sources_from_schema(
    schema_rows: list[SchemaMetadata],
    source_names: dict[str, str],
    source_types: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Group schema rows into source -> table -> columns structure.

    Returns a dict keyed by source_id (str) with the full source structure.
    """
    sources: dict[str, dict[str, Any]] = {}

    for row in schema_rows:
        sid = str(row.source_id)

        if sid not in sources:
            sources[sid] = {
                "source_id": sid,
                "source_type": source_types.get(sid, "unknown"),
                "source_name": source_names.get(sid, "Unknown"),
                "tables": {},
            }

        tables = sources[sid]["tables"]
        tname = row.table_name
        if tname not in tables:
            tables[tname] = {
                "table_name": tname,
                "columns": [],
            }

        tables[tname]["columns"].append(_build_column_entry(row))

    return sources


@router.get("/schema")
def get_unified_schema(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return a unified view of all data sources and their schemas.

    Aggregates SchemaMetadata from datasets and connections, groups by
    source -> table -> columns.  Sources are ordered by name.  Empty
    sources (those with no schema metadata) are included with an empty
    tables list.
    """
    # ---- Collect all known sources ----

    # 1. Datasets from the database
    dataset_stmt = select(Dataset).order_by(Dataset.name)
    datasets = list(db.execute(dataset_stmt).scalars().all())

    source_names: dict[str, str] = {}
    source_types: dict[str, str] = {}
    source_statuses: dict[str, str] = {}

    for ds in datasets:
        sid = str(ds.id)
        source_names[sid] = ds.name
        source_types[sid] = "dataset"
        source_statuses[sid] = ds.status

    # 2. Connections from the in-memory store
    for conn_id, record in connections_module._connections.items():
        sid = str(conn_id)
        source_names[sid] = record["name"]
        source_types[sid] = "connection"
        source_statuses[sid] = record.get("status", "disconnected")

    # ---- Fetch all schema metadata in a single query ----
    schema_stmt = select(SchemaMetadata).order_by(
        SchemaMetadata.source_id,
        SchemaMetadata.table_name,
        SchemaMetadata.column_name,
    )
    schema_rows = list(db.execute(schema_stmt).scalars().all())

    # Also include in-memory schema metadata for connections
    inmemory_schema: list[SchemaMetadata] = []
    for conn_id, meta_list in connections_module._schema_metadata.items():
        for meta in meta_list:
            # Create a lightweight object that mimics SchemaMetadata attributes
            obj = _InMemorySchema(
                source_id=meta["source_id"],
                source_type=meta["source_type"],
                table_name=meta["table_name"],
                column_name=meta["column_name"],
                data_type=meta["data_type"],
                is_nullable=meta["is_nullable"],
                is_primary_key=meta["is_primary_key"],
                foreign_key_ref=meta.get("foreign_key_ref"),
            )
            inmemory_schema.append(obj)  # type: ignore[arg-type]

    all_schema = list(schema_rows) + inmemory_schema  # type: ignore[operator]

    # ---- Build the grouped structure ----
    sources_map = _build_sources_from_schema(all_schema, source_names, source_types)

    # ---- Ensure empty sources are included ----
    for sid in source_names:
        if sid not in sources_map:
            sources_map[sid] = {
                "source_id": sid,
                "source_type": source_types[sid],
                "source_name": source_names[sid],
                "tables": {},
            }

    # ---- Convert tables dict to sorted list and build final response ----
    result_sources: list[dict[str, Any]] = []
    for sid, source in sources_map.items():
        tables_dict = source["tables"]
        source["tables"] = sorted(tables_dict.values(), key=lambda t: t["table_name"])
        result_sources.append(source)

    # Sort sources by name
    result_sources.sort(key=lambda s: s["source_name"].lower())

    logger.info(
        "schema_registry_fetched",
        source_count=len(result_sources),
        total_tables=sum(len(s["tables"]) for s in result_sources),
    )

    return {"sources": result_sources}


class _InMemorySchema:
    """Lightweight object that mimics SchemaMetadata attributes for in-memory data."""

    __slots__ = (
        "source_id",
        "source_type",
        "table_name",
        "column_name",
        "data_type",
        "is_nullable",
        "is_primary_key",
        "foreign_key_ref",
    )

    def __init__(
        self,
        source_id: Any,
        source_type: str,
        table_name: str,
        column_name: str,
        data_type: str,
        is_nullable: bool,
        is_primary_key: bool,
        foreign_key_ref: str | None,
    ) -> None:
        self.source_id = source_id
        self.source_type = source_type
        self.table_name = table_name
        self.column_name = column_name
        self.data_type = data_type
        self.is_nullable = is_nullable
        self.is_primary_key = is_primary_key
        self.foreign_key_ref = foreign_key_ref
