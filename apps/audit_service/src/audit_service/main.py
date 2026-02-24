"""Точка входа FastAPI: audit_service с lifespan (init DB)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from audit_service.database import init_db
from audit_service.routes_ingest import router as ingest_router
from audit_service.routes_metrics import router as metrics_router
from audit_service.routes_runs import router as runs_router
from audit_service.settings import Settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    init_db(settings)
    log.info("audit_service started, db=%s", settings.audit_db_path)
    yield
    # shutdown: nothing to close for SQLite


app = FastAPI(
    title="Audit Service",
    description="Приём событий аудита и метрики (SQLite)",
    lifespan=lifespan,
)


app.include_router(ingest_router)
app.include_router(metrics_router)
app.include_router(runs_router)


@app.get("/health")
def health():
    """Healthcheck для compose."""
    return {"status": "ok"}
