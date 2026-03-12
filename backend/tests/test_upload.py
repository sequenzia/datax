"""Tests for the dataset file upload endpoint.

Covers:
- Unit: File format validation, filename sanitization
- Integration: End-to-end upload flow, dataset record creation, large file streaming
- Edge cases: Empty file, duplicate filenames, special characters in filenames
- Error handling: Unsupported format, storage not writable
"""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.base import Base
from app.services.file_upload import (
    sanitize_filename,
    validate_file_format,
)


def _test_settings(
    db_path: Path | None = None,
    storage_path: str | None = None,
) -> Settings:
    """Create test settings with required fields."""
    db_url = f"sqlite:///{db_path}" if db_path else "sqlite:///:memory:"
    env = {
        "DATABASE_URL": db_url,
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    if storage_path:
        env["DATAX_STORAGE_PATH"] = storage_path
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Unit: File format validation
# ---------------------------------------------------------------------------


class TestValidateFileFormat:
    """Test file format validation logic."""

    def test_csv_format(self) -> None:
        assert validate_file_format("data.csv") == "csv"

    def test_xlsx_format(self) -> None:
        assert validate_file_format("report.xlsx") == "xlsx"

    def test_xls_format(self) -> None:
        assert validate_file_format("legacy.xls") == "xls"

    def test_parquet_format(self) -> None:
        assert validate_file_format("big_data.parquet") == "parquet"

    def test_json_format(self) -> None:
        assert validate_file_format("config.json") == "json"

    def test_case_insensitive(self) -> None:
        assert validate_file_format("DATA.CSV") == "csv"
        assert validate_file_format("Report.XLSX") == "xlsx"

    def test_unsupported_format_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            validate_file_format("document.doc")

    def test_no_extension_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            validate_file_format("noextension")

    def test_pdf_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            validate_file_format("report.pdf")

    def test_txt_raises(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            validate_file_format("notes.txt")


# ---------------------------------------------------------------------------
# Unit: Filename sanitization
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Test filename sanitization logic."""

    def test_normal_filename_preserved(self) -> None:
        result = sanitize_filename("sales_data.csv")
        assert result == "sales_data.csv"

    def test_special_chars_replaced(self) -> None:
        result = sanitize_filename("my file (v2) [final].csv")
        assert " " not in result
        assert "(" not in result
        assert ")" not in result
        assert "[" not in result
        assert "]" not in result
        assert result.endswith(".csv")

    def test_path_traversal_stripped(self) -> None:
        result = sanitize_filename("../../etc/passwd.csv")
        assert ".." not in result
        assert "/" not in result
        assert result.endswith(".csv")

    def test_directory_prefix_stripped(self) -> None:
        result = sanitize_filename("/Users/someone/data.csv")
        assert result.startswith("data")
        assert result.endswith(".csv")

    def test_consecutive_underscores_collapsed(self) -> None:
        result = sanitize_filename("a___b___c.csv")
        assert "___" not in result

    def test_unicode_chars_replaced(self) -> None:
        result = sanitize_filename("datos_en_espanol.csv")
        assert result.endswith(".csv")

    def test_empty_stem_generates_uuid(self) -> None:
        result = sanitize_filename("....csv")
        assert result.endswith(".csv")
        # stem should be a UUID hex fragment (8 chars)
        stem = Path(result).stem
        assert len(stem) == 8

    def test_extension_lowercased(self) -> None:
        result = sanitize_filename("DATA.CSV")
        assert result.endswith(".csv")

    def test_preserves_hyphens(self) -> None:
        result = sanitize_filename("my-data-file.csv")
        assert "my-data-file" in result


# ---------------------------------------------------------------------------
# Integration: End-to-end upload
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for file storage and test database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tmp_storage(tmp_dir):
    """Subdirectory for file uploads within the temp dir."""
    uploads = tmp_dir / "uploads"
    uploads.mkdir()
    return uploads


@pytest.fixture
def db_path(tmp_dir):
    """Path for the file-based SQLite test database."""
    return tmp_dir / "test.db"


@pytest.fixture
def app_with_storage(tmp_storage, db_path):
    """Create a FastAPI app with a file-based SQLite DB and test storage path."""
    settings = _test_settings(db_path=db_path, storage_path=str(tmp_storage))
    app = create_app(settings=settings)

    # Use file-based SQLite so background tasks share the same database
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    app.state.db_engine = engine
    app.state.session_factory = factory

    return app


@pytest.fixture
async def client(app_with_storage):
    """Create an async test client."""
    transport = ASGITransport(app=app_with_storage)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestUploadEndpoint:
    """Integration tests for the file upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_csv_returns_202(self, client, tmp_storage) -> None:
        """Uploading a CSV file returns 202 Accepted."""
        csv_content = b"id,name,value\n1,Alice,100\n2,Bob,200\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("test_data.csv", BytesIO(csv_content), "text/csv")},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_format"] == "csv"
        assert body["status"] == "processing"
        assert body["file_size_bytes"] == len(csv_content)
        assert body["id"] is not None
        assert body["name"] == "test_data"

    @pytest.mark.asyncio
    async def test_upload_json_returns_202(self, client, tmp_storage) -> None:
        """Uploading a JSON file returns 202 Accepted."""
        json_content = b'[{"id": 1, "name": "Alice"}]'
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("data.json", BytesIO(json_content), "application/json")},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_format"] == "json"

    @pytest.mark.asyncio
    async def test_upload_parquet_returns_202(self, client, tmp_storage) -> None:
        """Uploading a Parquet file returns 202 Accepted."""
        # Parquet files are binary; using a minimal valid content marker
        parquet_content = b"PAR1" + b"\x00" * 100
        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": (
                    "data.parquet",
                    BytesIO(parquet_content),
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_format"] == "parquet"

    @pytest.mark.asyncio
    async def test_upload_xlsx_returns_202(self, client, tmp_storage) -> None:
        """Uploading an Excel file returns 202 Accepted."""
        xlsx_content = b"\x50\x4b\x03\x04" + b"\x00" * 100  # ZIP magic bytes
        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": (
                    "report.xlsx",
                    BytesIO(xlsx_content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_format"] == "xlsx"

    @pytest.mark.asyncio
    async def test_upload_stores_file_on_disk(self, client, tmp_storage) -> None:
        """Uploaded file is actually written to the storage directory."""
        csv_content = b"id,name\n1,Alice\n"
        await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("disk_test.csv", BytesIO(csv_content), "text/csv")},
        )

        # Check that a file was created in the storage directory
        stored_files = list(tmp_storage.glob("*.csv"))
        assert len(stored_files) == 1
        assert stored_files[0].read_bytes() == csv_content

    @pytest.mark.asyncio
    async def test_upload_creates_dataset_record(self, client, app_with_storage) -> None:
        """Upload creates a Dataset record in the database."""
        csv_content = b"x,y\n1,2\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("record_test.csv", BytesIO(csv_content), "text/csv")},
        )
        dataset_id = response.json()["id"]

        # Verify the record exists via the GET endpoint
        get_response = await client.get(f"/api/v1/datasets/{dataset_id}")
        assert get_response.status_code == 200
        body = get_response.json()
        assert body["name"] == "record_test"
        assert body["file_format"] == "csv"
        assert body["file_size_bytes"] == len(csv_content)

    @pytest.mark.asyncio
    async def test_upload_file_size_accurate(self, client) -> None:
        """Reported file_size_bytes matches the actual uploaded content size."""
        content = b"a,b,c\n" + b"1,2,3\n" * 500
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("size_test.csv", BytesIO(content), "text/csv")},
        )

        assert response.status_code == 202
        assert response.json()["file_size_bytes"] == len(content)

    @pytest.mark.asyncio
    async def test_upload_custom_name(self, client) -> None:
        """Custom name overrides the filename-derived name."""
        csv_content = b"id\n1\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("file.csv", BytesIO(csv_content), "text/csv")},
            data={"name": "My Custom Dataset"},
        )

        assert response.status_code == 202
        assert response.json()["name"] == "My Custom Dataset"

    @pytest.mark.asyncio
    async def test_upload_status_trackable(self, client) -> None:
        """Dataset status is trackable after upload via GET endpoint."""
        csv_content = b"id\n1\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("status_test.csv", BytesIO(csv_content), "text/csv")},
        )
        dataset_id = response.json()["id"]

        # Status should be processing (or ready if background task ran already)
        get_response = await client.get(f"/api/v1/datasets/{dataset_id}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] in ["processing", "ready"]


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestUploadEdgeCases:
    """Edge case tests for file upload."""

    @pytest.mark.asyncio
    async def test_empty_file_rejected(self, client) -> None:
        """Empty file (0 bytes) is rejected with 400."""
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("empty.csv", BytesIO(b""), "text/csv")},
        )

        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "EMPTY_FILE"

    @pytest.mark.asyncio
    async def test_duplicate_filename_creates_unique_file(
        self, client, tmp_storage
    ) -> None:
        """Uploading the same filename twice creates two separate files."""
        csv_content = b"id\n1\n"

        # Upload first file
        resp1 = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("same_name.csv", BytesIO(csv_content), "text/csv")},
        )
        assert resp1.status_code == 202
        id1 = resp1.json()["id"]

        # Upload second file with same name
        resp2 = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("same_name.csv", BytesIO(csv_content), "text/csv")},
        )
        assert resp2.status_code == 202
        id2 = resp2.json()["id"]

        # They should be different datasets
        assert id1 != id2

        # Both files should exist on disk
        stored_files = list(tmp_storage.glob("*.csv"))
        assert len(stored_files) == 2

    @pytest.mark.asyncio
    async def test_special_chars_in_filename_sanitized(self, client) -> None:
        """Special characters in filename are sanitized."""
        csv_content = b"id\n1\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": (
                    "my file (v2) [final].csv",
                    BytesIO(csv_content),
                    "text/csv",
                )
            },
        )

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_large_file_streams_without_memory_issues(
        self, client, tmp_storage
    ) -> None:
        """Large files are streamed in chunks without loading entirely into memory.

        Tests with a 1MB file to verify chunked streaming works.
        """
        # Generate 1MB of CSV data
        header = b"id,value,description\n"
        row = b"12345,67890,some_description_text_that_is_reasonably_long\n"
        rows_needed = (1024 * 1024) // len(row)
        large_content = header + row * rows_needed

        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": ("large_data.csv", BytesIO(large_content), "text/csv")
            },
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_size_bytes"] == len(large_content)

        # Verify file was written correctly
        stored_files = list(tmp_storage.glob("*.csv"))
        assert len(stored_files) == 1
        assert stored_files[0].stat().st_size == len(large_content)


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestUploadErrorHandling:
    """Error handling tests for file upload."""

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self, client) -> None:
        """Unsupported file format returns 400 with UNSUPPORTED_FORMAT code."""
        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": (
                    "document.doc",
                    BytesIO(b"fake doc content"),
                    "application/msword",
                )
            },
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "UNSUPPORTED_FORMAT"
        assert "supported formats" in body["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_unsupported_pdf_returns_400(self, client) -> None:
        """PDF file returns 400."""
        response = await client.post(
            "/api/v1/datasets/upload",
            files={
                "file": (
                    "report.pdf",
                    BytesIO(b"fake pdf"),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "UNSUPPORTED_FORMAT"

    @pytest.mark.asyncio
    async def test_no_file_returns_422(self, client) -> None:
        """Request without a file returns 422 validation error."""
        response = await client.post("/api/v1/datasets/upload")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_storage_not_writable_returns_500(self, tmp_dir) -> None:
        """Non-writable storage path returns 500."""
        # Use a path that does not exist and cannot be created
        db_path = tmp_dir / "test_writable.db"
        settings = _test_settings(
            db_path=db_path,
            storage_path="/nonexistent/readonly/path",
        )
        app = create_app(settings=settings)
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        app.state.db_engine = engine
        app.state.session_factory = sessionmaker(
            bind=engine, autocommit=False, autoflush=False
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            response = await c.post(
                "/api/v1/datasets/upload",
                files={
                    "file": ("test.csv", BytesIO(b"id\n1\n"), "text/csv")
                },
            )

        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "STORAGE_ERROR"

    @pytest.mark.asyncio
    async def test_response_includes_created_at(self, client) -> None:
        """Upload response includes created_at timestamp."""
        csv_content = b"id\n1\n"
        response = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("ts_test.csv", BytesIO(csv_content), "text/csv")},
        )

        assert response.status_code == 202
        body = response.json()
        assert "created_at" in body
