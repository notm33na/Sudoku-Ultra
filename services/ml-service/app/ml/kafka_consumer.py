"""
kafka_consumer.py — Competitive event enrichment consumer.

Reads two Kafka topics and writes enriched events as JSONL files to a shared
data volume. Airflow DAGs later process these files into DuckDB analytics tables.

Topics consumed:
  game.session.completed      → enriched with anomaly score → data/events/sessions/
  multiplayer.match.completed → written verbatim          → data/events/matches/

Usage:
  python -m app.ml.kafka_consumer

Environment variables:
  KAFKA_BROKERS        comma-separated brokers   (default: kafka:9092)
  KAFKA_GROUP_ID       consumer group id         (default: ml-service-enrichment)
  EVENTS_DIR           writable data directory   (default: data/events)
  ANOMALY_ENRICH       1 to call anomaly_service (default: 1)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("kafka_consumer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ── Config ────────────────────────────────────────────────────────────────────

KAFKA_BROKERS: list[str] = os.getenv("KAFKA_BROKERS", "kafka:9092").split(",")
KAFKA_GROUP_ID: str = os.getenv("KAFKA_GROUP_ID", "ml-service-enrichment")
EVENTS_DIR: Path = Path(os.getenv("EVENTS_DIR", "data/events"))
ENRICH_ANOMALY: bool = os.getenv("ANOMALY_ENRICH", "1") == "1"

TOPIC_SESSION = "game.session.completed"
TOPIC_MATCH = "multiplayer.match.completed"

# ── JSONL Writer ──────────────────────────────────────────────────────────────


def _write_event(subdir: str, event: dict[str, Any]) -> None:
    """Append event as a JSONL line to a date-partitioned file."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = EVENTS_DIR / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}.jsonl"
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


# ── Anomaly enrichment ────────────────────────────────────────────────────────


def _enrich_session(event: dict[str, Any]) -> dict[str, Any]:
    """
    Attempt to score the session through AnomalyService.
    On any error, return the event unmodified (with null anomaly fields).
    """
    enriched = dict(event)
    enriched["anomaly_score"] = None
    enriched["is_anomalous"] = None
    enriched["enriched_at"] = datetime.now(timezone.utc).isoformat()

    if not ENRICH_ANOMALY:
        return enriched

    try:
        from app.services.anomaly_service import anomaly_service  # lazy import

        result = anomaly_service.score(
            time_elapsed_ms=event.get("time_elapsed_ms", 60_000),
            cells_filled=event.get("cells_filled", 45),
            errors_count=event.get("errors_count", 0),
            hints_used=event.get("hints_used", 0),
            difficulty=event.get("difficulty", "medium"),
        )
        enriched["anomaly_score"] = result["anomaly_score"]
        enriched["reconstruction_error"] = result["reconstruction_error"]
        enriched["is_anomalous"] = result["is_anomalous"]
    except Exception as exc:
        logger.warning("Anomaly enrichment failed for session %s: %s", event.get("session_id"), exc)

    return enriched


# ── Message dispatch ──────────────────────────────────────────────────────────


def _handle_session(raw: bytes) -> None:
    try:
        event: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in session event, skipping.")
        return

    enriched = _enrich_session(event)
    _write_event("sessions", enriched)
    logger.info(
        "session %s enriched — anomalous=%s score=%.4f",
        enriched.get("session_id", "?"),
        enriched.get("is_anomalous"),
        enriched.get("anomaly_score") or 0.0,
    )


def _handle_match(raw: bytes) -> None:
    try:
        event: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in match event, skipping.")
        return

    event["consumed_at"] = datetime.now(timezone.utc).isoformat()
    _write_event("matches", event)
    logger.info(
        "match %s recorded — winner=%s delta=%s",
        event.get("match_id", "?"),
        event.get("winner_id", "?"),
        event.get("elo_delta", "?"),
    )


# ── Consumer loop ─────────────────────────────────────────────────────────────

_running = True


def _shutdown(signum: int, _frame: Any) -> None:
    global _running
    logger.info("Shutdown signal received (%s), draining…", signum)
    _running = False


def run() -> None:
    """
    Main consumer loop. Imports kafka-python lazily so the module can be
    imported in tests without kafka-python installed.
    """
    try:
        from kafka import KafkaConsumer  # type: ignore[import]
        from kafka.errors import NoBrokersAvailable  # type: ignore[import]
    except ImportError:
        logger.error("kafka-python not installed. Add kafka-python to requirements.txt.")
        sys.exit(1)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    consumer: Any = None
    retry_delay = 5

    while _running:
        try:
            logger.info("Connecting to Kafka brokers: %s", KAFKA_BROKERS)
            consumer = KafkaConsumer(
                TOPIC_SESSION,
                TOPIC_MATCH,
                bootstrap_servers=KAFKA_BROKERS,
                group_id=KAFKA_GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda b: b,  # raw bytes — we decode per handler
                consumer_timeout_ms=1_000,       # poll returns after 1 s if no messages
            )
            logger.info("Consumer connected. Subscribed to [%s, %s].", TOPIC_SESSION, TOPIC_MATCH)
            retry_delay = 5  # reset backoff on successful connect

            while _running:
                for msg in consumer:
                    if not _running:
                        break
                    if msg.topic == TOPIC_SESSION:
                        _handle_session(msg.value)
                    elif msg.topic == TOPIC_MATCH:
                        _handle_match(msg.value)

        except NoBrokersAvailable:
            logger.warning("No Kafka brokers available. Retrying in %ds…", retry_delay)
        except Exception as exc:
            logger.exception("Unexpected consumer error: %s", exc)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass
                consumer = None

        if _running:
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # exponential back-off, cap 60 s

    logger.info("Consumer shut down cleanly.")


if __name__ == "__main__":
    run()
