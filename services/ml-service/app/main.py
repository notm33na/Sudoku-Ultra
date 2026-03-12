"""
Sudoku Ultra — ML Service Application Factory

Creates and configures the FastAPI application with middleware,
routers, and lifecycle events.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging import setup_logging
from app.middleware import RequestLoggingMiddleware, register_exception_handlers
from app.routers import health, classify, scan, recommend, churn
from app.services.model_registry import model_registry

logger = setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.VERSION} ({settings.ENV})")
    await model_registry.load_all()
    logger.info("ML Service ready to serve requests")
    yield
    logger.info("Shutting down ML Service")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Sudoku Ultra ML Service",
        description="ML/AI microservice — difficulty classification, puzzle scanning, adaptive recommendations",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request Logging ───────────────────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(classify.router)
    app.include_router(scan.router)
    app.include_router(recommend.router)
    app.include_router(churn.router)

    return app
