"""
D8 — MLOps Pipeline Tests

Covers:
  - ModelVersionRegistry: register, promote, list, hash, auto-promote
  - MonitoringService: record_prediction, get_metrics, detect_drift, alerts
  - MLOps API router: /api/v1/mlops/* endpoints (via AsyncClient)
"""

import json
import pytest
import pytest_asyncio
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from app.services.model_version_registry import ModelVersionRegistry
from app.services.monitoring_service import MonitoringService
from app.main import create_app


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path: Path) -> ModelVersionRegistry:
    """Fresh registry backed by a temp file."""
    manifest = tmp_path / "test_manifest.json"
    return ModelVersionRegistry(manifest_path=manifest)


@pytest.fixture
def monitor() -> MonitoringService:
    """Fresh monitoring service (in-memory, no shared state)."""
    return MonitoringService()


@pytest_asyncio.fixture
async def client():
    """Async test client wired to a fresh app instance."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── ModelVersionRegistry ────────────────────────────────────────────────────


class TestModelVersionRegistry:

    def test_register_first_version_auto_promotes_to_production(self, registry: ModelVersionRegistry):
        entry = registry.register_model(
            name="difficulty-classifier",
            version="1.0.0",
            model_path="/nonexistent/model.pkl",
            metrics={"test_accuracy": 0.92},
        )
        assert entry["stage"] == "production"
        assert registry.manifest["models"]["difficulty-classifier"]["production"] == "1.0.0"

    def test_register_second_version_stays_in_development(self, registry: ModelVersionRegistry):
        registry.register_model("m", "1.0.0", "/fake.pkl", {})
        entry = registry.register_model("m", "1.1.0", "/fake.pkl", {}, stage="development")
        assert entry["stage"] == "development"
        # Previous production unchanged
        assert registry.manifest["models"]["m"]["production"] == "1.0.0"

    def test_promote_to_production_archives_previous(self, registry: ModelVersionRegistry):
        registry.register_model("m", "1.0.0", "/fake.pkl", {})
        registry.register_model("m", "2.0.0", "/fake.pkl", {}, stage="staging")
        success = registry.promote("m", "2.0.0", "production")

        assert success is True
        assert registry.manifest["models"]["m"]["production"] == "2.0.0"
        v1 = registry.manifest["models"]["m"]["versions"]["1.0.0"]
        assert v1["stage"] == "archived"

    def test_promote_unknown_model_returns_false(self, registry: ModelVersionRegistry):
        assert registry.promote("ghost", "1.0.0", "production") is False

    def test_promote_unknown_version_returns_false(self, registry: ModelVersionRegistry):
        registry.register_model("m", "1.0.0", "/fake.pkl", {})
        assert registry.promote("m", "9.9.9", "production") is False

    def test_get_production_model(self, registry: ModelVersionRegistry):
        registry.register_model("m", "1.0.0", "/fake.pkl", {"acc": 0.9})
        entry = registry.get_production_model("m")
        assert entry is not None
        assert entry["version"] == "1.0.0"
        assert entry["metrics"]["acc"] == 0.9

    def test_get_production_model_no_model_returns_none(self, registry: ModelVersionRegistry):
        assert registry.get_production_model("ghost") is None

    def test_list_models_empty(self, registry: ModelVersionRegistry):
        assert registry.list_models() == {}

    def test_list_models_shows_latest_and_production(self, registry: ModelVersionRegistry):
        registry.register_model("m", "1.0.0", "/fake.pkl", {})
        registry.register_model("m", "2.0.0", "/fake.pkl", {}, stage="staging")
        listing = registry.list_models()

        assert "m" in listing
        assert listing["m"]["latest"] == "2.0.0"
        assert listing["m"]["production"] == "1.0.0"
        assert set(listing["m"]["versions"]) == {"1.0.0", "2.0.0"}

    def test_manifest_persisted_to_disk(self, registry: ModelVersionRegistry, tmp_path: Path):
        registry.register_model("m", "1.0.0", "/fake.pkl", {"acc": 0.95})
        # Reload from disk
        reloaded = ModelVersionRegistry(manifest_path=registry.manifest_path)
        assert "m" in reloaded.manifest["models"]
        assert reloaded.manifest["models"]["m"]["versions"]["1.0.0"]["metrics"]["acc"] == 0.95

    def test_tags_stored_correctly(self, registry: ModelVersionRegistry):
        entry = registry.register_model(
            "m", "1.0.0", "/fake.pkl", {},
            tags={"trigger": "ci", "sha": "abc123"},
        )
        assert entry["tags"]["trigger"] == "ci"
        assert entry["tags"]["sha"] == "abc123"

    def test_file_hash_none_for_missing_file(self, registry: ModelVersionRegistry):
        entry = registry.register_model("m", "1.0.0", "/does/not/exist.pkl", {})
        assert entry["file_hash"] is None

    def test_file_hash_computed_for_existing_file(self, registry: ModelVersionRegistry, tmp_path: Path):
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"fake model bytes")
        entry = registry.register_model("m", "1.0.0", str(model_file), {})
        assert entry["file_hash"] is not None
        assert len(entry["file_hash"]) == 64  # SHA-256 hex


# ─── MonitoringService ───────────────────────────────────────────────────────


class TestMonitoringService:

    def test_metrics_empty_before_any_predictions(self, monitor: MonitoringService):
        metrics = monitor.get_metrics()
        assert metrics["total_predictions"] == 0
        assert metrics["latency"] == {}
        assert metrics["accuracy"] is None

    def test_record_prediction_increments_count(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.9, 12.5)
        monitor.record_prediction("m", "hard", 0.75, 18.0)
        metrics = monitor.get_metrics()
        assert metrics["total_predictions"] == 2

    def test_latency_percentiles_correct(self, monitor: MonitoringService):
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            monitor.record_prediction("m", "easy", 0.9, float(ms))
        metrics = monitor.get_metrics()
        assert metrics["latency"]["mean_ms"] == pytest.approx(55.0)
        assert metrics["latency"]["p50_ms"] > 0
        assert metrics["latency"]["p95_ms"] >= metrics["latency"]["p50_ms"]

    def test_accuracy_calculated_from_labeled_predictions(self, monitor: MonitoringService):
        monitor.predictions.append({"model": "m", "predicted": "easy", "actual": "easy", "confidence": 0.9, "timestamp": 0})
        monitor.predictions.append({"model": "m", "predicted": "hard", "actual": "easy", "confidence": 0.8, "timestamp": 0})
        monitor.latencies.append(10.0)
        monitor.latencies.append(10.0)
        metrics = monitor.get_metrics()
        assert metrics["accuracy"] == pytest.approx(0.5)

    def test_accuracy_none_without_labels(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.9, 10.0)  # no actual
        metrics = monitor.get_metrics()
        assert metrics["accuracy"] is None

    def test_confidence_below_70_pct_tracked(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.5, 10.0)   # below 0.7
        monitor.record_prediction("m", "hard", 0.95, 10.0)  # above 0.7
        metrics = monitor.get_metrics()
        assert metrics["confidence"]["below_70_pct"] == pytest.approx(0.5)

    def test_high_latency_generates_alert(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.9, 600.0)  # > 500ms threshold
        metrics = monitor.get_metrics()
        assert len(metrics["alerts"]) >= 1
        assert any("latency" in a["message"].lower() for a in metrics["alerts"])

    def test_very_low_confidence_generates_alert(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.1, 10.0)  # < 0.3 threshold
        metrics = monitor.get_metrics()
        assert any("confidence" in a["message"].lower() for a in metrics["alerts"])

    def test_class_distribution_tracked(self, monitor: MonitoringService):
        monitor.record_prediction("m", "easy", 0.9, 10.0)
        monitor.record_prediction("m", "easy", 0.85, 10.0)
        monitor.record_prediction("m", "hard", 0.8, 10.0)
        metrics = monitor.get_metrics()
        assert metrics["class_distribution"]["easy"] == 2
        assert metrics["class_distribution"]["hard"] == 1

    def test_detect_drift_no_data_returns_no_drift(self, monitor: MonitoringService):
        result = monitor.detect_drift({"easy": 0.5, "hard": 0.5})
        assert result["drift_detected"] is False
        assert result["status"] == "no_data"

    def test_detect_drift_matching_distribution_no_drift(self, monitor: MonitoringService):
        # Inject 100 predictions matching reference exactly
        for _ in range(50):
            monitor.record_prediction("m", "easy", 0.9, 10.0)
        for _ in range(50):
            monitor.record_prediction("m", "hard", 0.85, 10.0)

        result = monitor.detect_drift({"easy": 0.5, "hard": 0.5})
        assert result["psi"] < 0.1
        assert result["status"] == "no_drift"

    def test_detect_drift_mismatched_distribution_flags_significant(self, monitor: MonitoringService):
        # All predictions are "easy" but reference expects even split
        for _ in range(100):
            monitor.record_prediction("m", "easy", 0.9, 10.0)

        result = monitor.detect_drift({"easy": 0.2, "hard": 0.4, "medium": 0.4})
        assert result["drift_detected"] is True
        assert result["psi"] > 0.1

    def test_psi_significant_drift_adds_alert(self, monitor: MonitoringService):
        for _ in range(100):
            monitor.record_prediction("m", "extreme", 0.9, 10.0)

        monitor.detect_drift({"easy": 0.33, "medium": 0.33, "hard": 0.34})
        metrics = monitor.get_metrics()
        assert any("drift" in a["message"].lower() for a in metrics["alerts"])


# ─── MLOps API Router ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMlopsRouter:

    async def test_list_models_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/mlops/models")
        assert resp.status_code == 200
        # Returns dict (may be empty or have models from shared singleton)
        assert isinstance(resp.json(), dict)

    async def test_register_model(self, client: AsyncClient):
        resp = await client.post("/api/v1/mlops/models/register", json={
            "name": "test-model",
            "version": "1.0.0",
            "model_path": "/fake/test.pkl",
            "metrics": {"accuracy": 0.91},
            "stage": "staging",
            "tags": {"env": "test"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "registered"
        assert body["entry"]["name"] == "test-model"
        assert body["entry"]["version"] == "1.0.0"

    async def test_promote_model(self, client: AsyncClient):
        # Register first
        await client.post("/api/v1/mlops/models/register", json={
            "name": "promo-model",
            "version": "1.0.0",
            "model_path": "/fake/promo.pkl",
            "metrics": {},
        })
        await client.post("/api/v1/mlops/models/register", json={
            "name": "promo-model",
            "version": "2.0.0",
            "model_path": "/fake/promo.pkl",
            "metrics": {},
            "stage": "staging",
        })

        resp = await client.post("/api/v1/mlops/models/promote", json={
            "name": "promo-model",
            "version": "2.0.0",
            "target_stage": "production",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "promoted"
        assert body["stage"] == "production"

    async def test_promote_unknown_model_returns_failed(self, client: AsyncClient):
        resp = await client.post("/api/v1/mlops/models/promote", json={
            "name": "ghost-model",
            "version": "1.0.0",
            "target_stage": "production",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    async def test_get_production_model_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/mlops/models/nonexistent-model/production")
        assert resp.status_code == 200
        assert "error" in resp.json()

    async def test_monitoring_metrics_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/v1/mlops/monitoring/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_predictions" in body
        assert "latency" in body
        assert "confidence" in body
        assert "alerts" in body

    async def test_drift_check_endpoint(self, client: AsyncClient):
        resp = await client.post("/api/v1/mlops/monitoring/drift", json={
            "reference_distribution": {
                "easy": 0.25,
                "medium": 0.25,
                "hard": 0.25,
                "extreme": 0.25,
            }
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "drift_detected" in body
        assert "psi" in body
        assert "status" in body

    async def test_retrain_trigger_returns_job_id(self, client: AsyncClient):
        resp = await client.post("/api/v1/mlops/retrain", json={
            "model_name": "difficulty-classifier",
            "n_samples": 100,
            "n_trials": 5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert "job_id" in body
        assert len(body["job_id"]) == 8

    async def test_retrain_response_shape(self, client: AsyncClient):
        """Retraining endpoint returns job metadata without waiting for training to finish."""
        resp = await client.post("/api/v1/mlops/retrain", json={
            "model_name": "adaptive-difficulty",
            "n_samples": 100,
            "n_trials": 5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["model_name"] == "adaptive-difficulty"
        assert "job_id" in body
        assert "message" in body
