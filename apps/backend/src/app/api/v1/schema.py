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

from app.dependencies import get_db
from app.logging import get_logger
from app.models.orm import Connection, Dataset, SchemaMetadata

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

    for ds in datasets:
        sid = str(ds.id)
        source_names[sid] = ds.name
        source_types[sid] = "dataset"

    # 2. Connections from the database
    conn_stmt = select(Connection).order_by(Connection.name)
    connections = list(db.execute(conn_stmt).scalars().all())

    for conn in connections:
        sid = str(conn.id)
        source_names[sid] = conn.name
        source_types[sid] = "connection"

    # ---- Fetch all schema metadata in a single query ----
    schema_stmt = select(SchemaMetadata).order_by(
        SchemaMetadata.source_id,
        SchemaMetadata.table_name,
        SchemaMetadata.column_name,
    )
    schema_rows = list(db.execute(schema_stmt).scalars().all())

    # ---- Build the grouped structure ----
    sources_map = _build_sources_from_schema(schema_rows, source_names, source_types)

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
