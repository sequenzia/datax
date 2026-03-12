"""Dataset-related enums and constants.

The SQLAlchemy ORM model for Dataset lives in ``app.models.orm``.
This module provides enums and constants used by both the ORM layer
and the DuckDB integration services.
"""

from __future__ import annotations

from enum import StrEnum


class DatasetStatus(StrEnum):
    """Processing status for a dataset."""

    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class FileFormat(StrEnum):
    """Supported file formats for dataset upload."""

    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    PARQUET = "parquet"
    JSON = "json"
