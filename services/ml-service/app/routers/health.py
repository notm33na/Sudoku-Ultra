"""
Health check router.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.services.model_registry import model_registry

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    timestamp: str
    models_loaded: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check with model status."""
    return HealthResponse(
        status="ok",
        service=settings.SERVICE_NAME,
        version=settings.VERSION,
        environment=settings.ENV,
        timestamp=datetime.now(timezone.utc).isoformat(),
        models_loaded=model_registry.list_models(),
    )
