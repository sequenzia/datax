"""File upload service for streaming file storage and dataset creation.

Handles:
- Streaming file writes to disk without loading the entire file into memory
- Filename sanitization for safe filesystem and display names
- Unique DuckDB table name generation
- Background DuckDB registration triggering
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.logging import get_logger
from app.models.dataset import FileFormat

logger = get_logger(__name__)

# Chunk size for streaming file writes (64 KB)
UPLOAD_CHUNK_SIZE = 64 * 1024

# Allowed file extensions mapped to FileFormat values
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".csv": FileFormat.CSV,
    ".xlsx": FileFormat.XLSX,
    ".xls": FileFormat.XLS,
    ".parquet": FileFormat.PARQUET,
    ".json": FileFormat.JSON,
}

SUPPORTED_FORMATS_STR = "csv, xlsx, xls, parquet, json"


def validate_file_format(filename: str) -> str:
    """Validate that the filename has a supported extension.

    Args:
        filename: Original filename from the upload.

    Returns:
        The file format string (e.g., "csv", "xlsx").

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File format {ext or '(none)'} is not supported. "
            f"Supported formats: {SUPPORTED_FORMATS_STR}"
        )
    return ALLOWED_EXTENSIONS[ext]


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe filesystem storage.

    - Strips directory components (path traversal prevention)
    - Replaces non-alphanumeric characters (except dots, hyphens, underscores) with underscores
    - Collapses consecutive underscores
    - Trims leading/trailing underscores and dots
    - Falls back to a UUID fragment if the result is empty

    Args:
        filename: Original filename from the upload.

    Returns:
        A sanitized filename safe for filesystem use.
    """
    # Strip directory components
    name = Path(filename).name

    # Separate stem and extension
    stem = Path(name).stem
    ext = Path(name).suffix.lower()

    # Replace non-safe characters with underscores
    stem = re.sub(r"[^a-zA-Z0-9._-]", "_", stem)

    # Collapse consecutive underscores
    stem = re.sub(r"_+", "_", stem).strip("_.")

    if not stem:
        stem = uuid.uuid4().hex[:8]

    return f"{stem}{ext}"


def generate_unique_filename(sanitized_name: str, storage_dir: Path) -> str:
    """Generate a unique filename by appending a UUID suffix if needed.

    Prevents collisions when the same filename is uploaded multiple times.

    Args:
        sanitized_name: Already-sanitized filename.
        storage_dir: Directory where the file will be stored.

    Returns:
        A unique filename in the storage directory.
    """
    stem = Path(sanitized_name).stem
    ext = Path(sanitized_name).suffix

    # Always append a short UUID to ensure uniqueness
    unique_suffix = uuid.uuid4().hex[:8]
    unique_name = f"{stem}_{unique_suffix}{ext}"

    return unique_name


def ensure_storage_dir(storage_path: Path) -> Path:
    """Ensure the storage directory exists and is writable.

    Args:
        storage_path: Path to the storage directory.

    Returns:
        The storage path.

    Raises:
        OSError: If the directory cannot be created or is not writable.
    """
    storage_path.mkdir(parents=True, exist_ok=True)

    # Verify we can write to it
    test_file = storage_path / ".write_test"
    try:
        test_file.touch()
        test_file.unlink()
    except OSError as exc:
        raise OSError(f"Storage directory is not writable: {storage_path}") from exc

    return storage_path
