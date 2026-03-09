"""
Pytest fixtures for ML service tests.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.services.model_registry import ModelRegistry


@pytest.fixture
def app():
    """Create a fresh FastAPI app for testing."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def model_registry():
    """Fresh model registry for testing."""
    return ModelRegistry()
