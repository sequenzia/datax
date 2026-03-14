from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.config import Settings, get_settings
from app.database import create_db_engine, create_session_factory
from app.errors import register_exception_handlers
from app.logging import get_logger, setup_logging
from app.models.dataset import DatasetStatus
from app.models.orm import Dataset
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager
from app.shutdown import ShutdownManager


def _rehydrate_duckdb_views(
    session_factory: sessionmaker[Session],
    duckdb_mgr: DuckDBManager,
) -> None:
    """Re-create DuckDB views for all ready datasets after a restart.

    DuckDB runs in-memory, so view definitions are lost when the process
    exits. The underlying files and PostgreSQL metadata survive, so this
    function bridges the two by re-registering each file as a view.
    """
    logger = get_logger(__name__)

    with session_factory() as session:
        datasets = (
            session.execute(
                select(Dataset).where(Dataset.status == DatasetStatus.READY)
            )
            .scalars()
            .all()
        )

        registered = 0
        errors = 0

        for ds in datasets:
            file_path = Path(ds.file_path)

            if not file_path.exists():
                logger.warning(
                    "rehydrate_file_missing",
                    dataset_id=str(ds.id),
                    file_path=str(file_path),
                )
                ds.status = DatasetStatus.ERROR
                errors += 1
                continue

            try:
                result = duckdb_mgr.register_file(
                    file_path, ds.duckdb_table_name, ds.file_format
                )
                if result.is_success:
                    registered += 1
                else:
                    logger.warning(
                        "rehydrate_registration_failed",
                        dataset_id=str(ds.id),
                        error=result.error_message,
                    )
                    errors += 1
            except Exception:
                logger.warning(
                    "rehydrate_registration_error",
                    dataset_id=str(ds.id),
                    exc_info=True,
                )
                errors += 1

        session.commit()

    logger.info(
        "duckdb_rehydration_complete",
        registered=registered,
        errors=errors,
        total=len(datasets),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic."""
    logger = get_logger(__name__)
    logger.info("application_startup", version="0.1.0")

    # Install graceful shutdown handlers (SIGTERM / SIGINT).
    shutdown_mgr: ShutdownManager = app.state.shutdown_manager
    try:
        shutdown_mgr.install_signal_handlers()
    except Exception:
        # Signal handlers cannot be installed in some test/thread contexts.
        logger.debug("signal_handlers_skipped", reason="not_main_thread_or_no_loop")

    # Re-register DuckDB views for datasets that survived a restart.
    try:
        _rehydrate_duckdb_views(
            session_factory=app.state.session_factory,
            duckdb_mgr=app.state.duckdb_manager,
        )
    except Exception:
        logger.error("duckdb_rehydration_failed", exc_info=True)

    yield

    # --- Graceful shutdown ---
    logger.info("application_shutdown_started")
    await shutdown_mgr.wait_for_drain()

    # Close connection manager pools
    if hasattr(app.state, "connection_manager"):
        app.state.connection_manager.close_all()

    # Close DuckDB connection
    if hasattr(app.state, "duckdb_manager"):
        app.state.duckdb_manager.close()

    logger.info("application_shutdown_complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Use as uvicorn factory: ``uvicorn app.main:create_app --factory``
    Or pass explicit settings for testing.
    """
    setup_logging()
    logger = get_logger(__name__)

    if settings is None:
        # Load .env files into os.environ so modules that read os.environ
        # directly (encryption, provider_service) see the values.
        # override=False means real env vars take precedence.
        project_root = Path(__file__).resolve().parents[4]
        load_dotenv(project_root / ".env", override=False)
        load_dotenv(project_root / ".env.local", override=False)
        settings = get_settings()

    app = FastAPI(
        title="DataX",
        description="AI-native data analytics platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Attach settings to app state for dependency injection.
    app.state.settings = settings

    # Attach shutdown manager to app state so handlers can access it.
    app.state.shutdown_manager = ShutdownManager()

    # Attach database session factory for PostgreSQL app state.
    engine = create_db_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)

    # Attach DuckDB manager for file-based analytics.
    app.state.duckdb_manager = DuckDBManager()

    # Attach connection manager for external database connections.
    app.state.connection_manager = ConnectionManager()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # Root-level health and readiness probes
    app.include_router(health_router)

    # API routers
    app.include_router(v1_router)

    logger.info(
        "application_configured",
        cors_origins=settings.cors_origins,
        storage_path=str(settings.datax_storage_path),
    )

    return app
