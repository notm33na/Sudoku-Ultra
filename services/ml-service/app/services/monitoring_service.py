"""
MLOps monitoring service.

Tracks prediction latency, accuracy metrics, and data drift detection
for deployed models. Provides alerting thresholds.
"""

import time
from collections import deque
from typing import Any

import numpy as np

from app.logging import setup_logging

logger = setup_logging()


class MonitoringService:
    """
    Real-time model monitoring: latency, accuracy, and drift.
    Uses a rolling window of recent predictions for metrics.
    """

    WINDOW_SIZE = 1000  # Rolling window for metrics

    def __init__(self) -> None:
        self.predictions: deque[dict] = deque(maxlen=self.WINDOW_SIZE)
        self.latencies: deque[float] = deque(maxlen=self.WINDOW_SIZE)
        self._alerts: list[dict] = []

    def record_prediction(
        self,
        model_name: str,
        predicted: str,
        confidence: float,
        latency_ms: float,
        actual: str | None = None,
    ) -> None:
        """Record a prediction for monitoring."""
        self.predictions.append({
            "model": model_name,
            "predicted": predicted,
            "confidence": confidence,
            "actual": actual,
            "timestamp": time.time(),
        })
        self.latencies.append(latency_ms)

        # Check thresholds
        self._check_latency_alert(latency_ms)
        self._check_confidence_alert(confidence)

    def get_metrics(self) -> dict[str, Any]:
        """Get current monitoring metrics."""
        if not self.latencies:
            return {
                "total_predictions": 0,
                "latency": {},
                "confidence": {},
                "accuracy": None,
                "alerts": [],
            }

        latency_arr = np.array(list(self.latencies))
        confidences = [p["confidence"] for p in self.predictions]
        conf_arr = np.array(confidences)

        # Accuracy (only where actual labels are available)
        labeled = [p for p in self.predictions if p.get("actual") is not None]
        accuracy = None
        if labeled:
            correct = sum(1 for p in labeled if p["predicted"] == p["actual"])
            accuracy = round(correct / len(labeled), 4)

        # Class distribution
        class_dist = {}
        for p in self.predictions:
            cls = p["predicted"]
            class_dist[cls] = class_dist.get(cls, 0) + 1

        return {
            "total_predictions": len(self.predictions),
            "latency": {
                "mean_ms": round(float(latency_arr.mean()), 2),
                "p50_ms": round(float(np.percentile(latency_arr, 50)), 2),
                "p95_ms": round(float(np.percentile(latency_arr, 95)), 2),
                "p99_ms": round(float(np.percentile(latency_arr, 99)), 2),
                "max_ms": round(float(latency_arr.max()), 2),
            },
            "confidence": {
                "mean": round(float(conf_arr.mean()), 4),
                "min": round(float(conf_arr.min()), 4),
                "below_70_pct": round(float((conf_arr < 0.7).mean()), 4),
            },
            "accuracy": accuracy,
            "class_distribution": class_dist,
            "alerts": self._alerts[-10:],  # Last 10 alerts
        }

    def detect_drift(self, reference_distribution: dict[str, float]) -> dict[str, Any]:
        """
        Detect class distribution drift vs. a reference.

        Uses Population Stability Index (PSI) as the drift metric.
        PSI < 0.1: no drift, 0.1–0.25: moderate, > 0.25: significant.
        """
        if not self.predictions:
            return {"drift_detected": False, "psi": 0.0, "status": "no_data"}

        # Current distribution
        class_dist = {}
        total = len(self.predictions)
        for p in self.predictions:
            cls = p["predicted"]
            class_dist[cls] = class_dist.get(cls, 0) + 1

        current = {k: v / total for k, v in class_dist.items()}

        # Calculate PSI
        all_classes = set(list(reference_distribution.keys()) + list(current.keys()))
        psi = 0.0
        for cls in all_classes:
            ref = max(reference_distribution.get(cls, 0.001), 0.001)
            cur = max(current.get(cls, 0.001), 0.001)
            psi += (cur - ref) * np.log(cur / ref)

        psi = round(float(psi), 4)

        if psi > 0.25:
            status = "significant_drift"
            self._add_alert("HIGH", f"Significant distribution drift detected (PSI={psi})")
        elif psi > 0.1:
            status = "moderate_drift"
        else:
            status = "no_drift"

        return {
            "drift_detected": psi > 0.1,
            "psi": psi,
            "status": status,
            "current_distribution": current,
            "reference_distribution": reference_distribution,
        }

    def _check_latency_alert(self, latency_ms: float) -> None:
        if latency_ms > 500:
            self._add_alert("WARNING", f"High latency: {latency_ms:.0f}ms")

    def _check_confidence_alert(self, confidence: float) -> None:
        if confidence < 0.3:
            self._add_alert("WARNING", f"Very low confidence: {confidence:.2f}")

    def _add_alert(self, severity: str, message: str) -> None:
        self._alerts.append({
            "severity": severity,
            "message": message,
            "timestamp": time.time(),
        })
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-50:]
        logger.warning(f"[Monitor] {severity}: {message}")


# Singleton
monitoring_service = MonitoringService()
