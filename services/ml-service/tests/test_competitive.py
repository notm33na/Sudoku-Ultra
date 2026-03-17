"""
test_competitive.py — pytest suite for D6 competitive analytics.

Tests are grouped:
  - KafkaConsumer helpers (unit, no Kafka required)
  - CompetitiveDuckdbService (unit, in-memory DuckDB)
  - FastAPI /api/v1/competitive/* endpoints (integration via TestClient)
  - Airflow DAG task functions (unit, tmp_path DuckDB)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_db(path: str) -> duckdb.DuckDBPyConnection:
    """Create an in-memory or file DuckDB with the competitive schema."""
    conn = duckdb.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS competitive_matches (
            match_id VARCHAR PRIMARY KEY,
            room_id VARCHAR, winner_id VARCHAR, loser_id VARCHAR,
            winner_elo_before INTEGER, winner_elo_after INTEGER,
            loser_elo_before INTEGER, loser_elo_after INTEGER,
            elo_delta INTEGER, difficulty VARCHAR, end_reason VARCHAR,
            duration_ms INTEGER, completed_at TIMESTAMP, consumed_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enriched_sessions (
            session_id VARCHAR PRIMARY KEY,
            user_id VARCHAR, puzzle_id VARCHAR, difficulty VARCHAR,
            time_elapsed_ms INTEGER, score INTEGER, hints_used INTEGER,
            errors_count INTEGER, completed_at TIMESTAMP,
            anomaly_score DOUBLE, reconstruction_error DOUBLE,
            is_anomalous BOOLEAN, enriched_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_trends (
            date DATE, user_id VARCHAR, matches_played INTEGER,
            wins INTEGER, losses INTEGER,
            elo_start INTEGER, elo_end INTEGER, elo_delta INTEGER,
            PRIMARY KEY (date, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
            snapshot_date DATE, rank INTEGER,
            user_id VARCHAR, elo_rating INTEGER, wins INTEGER, losses INTEGER,
            PRIMARY KEY (snapshot_date, rank)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_stats_daily (
            date DATE PRIMARY KEY, total_matches INTEGER,
            avg_duration_ms DOUBLE, avg_elo_delta DOUBLE,
            difficulty_breakdown VARCHAR, end_reason_breakdown VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_reports_daily (
            date DATE PRIMARY KEY, total_sessions INTEGER,
            flagged_count INTEGER, flag_rate DOUBLE, avg_anomaly_score DOUBLE
        )
    """)
    return conn


def _seed_match(conn: duckdb.DuckDBPyConnection, match_id: str = "m1",
                winner_id: str = "u1", loser_id: str = "u2",
                elo_delta: int = 16, difficulty: str = "medium",
                end_reason: str = "completion",
                completed_at: str = "2026-03-13 12:00:00") -> None:
    conn.execute(
        """INSERT OR IGNORE INTO competitive_matches VALUES
           (?,?,?,?,1200,1216,1200,1184,?,?,?,180000,?,CURRENT_TIMESTAMP)""",
        [match_id, "room-1", winner_id, loser_id, elo_delta,
         difficulty, end_reason, completed_at],
    )


def _seed_session(conn: duckdb.DuckDBPyConnection, session_id: str = "s1",
                  is_anomalous: bool = False,
                  completed_at: str = "2026-03-13 10:00:00") -> None:
    conn.execute(
        """INSERT OR IGNORE INTO enriched_sessions VALUES
           (?,?,?,?,300000,1000,1,3,?,0.1,0.05,?,CURRENT_TIMESTAMP)""",
        [session_id, "u1", "p1", "medium", completed_at, is_anomalous],
    )


# ─── KafkaConsumer helpers ─────────────────────────────────────────────────────


class TestKafkaConsumerHelpers:
    def test_write_event_creates_jsonl(self, tmp_path: Path) -> None:
        from app.ml import kafka_consumer

        original = kafka_consumer.EVENTS_DIR
        kafka_consumer.EVENTS_DIR = tmp_path
        try:
            kafka_consumer._write_event("sessions", {"session_id": "s1", "score": 100})
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            out = tmp_path / "sessions" / f"{today}.jsonl"
            assert out.exists()
            data = json.loads(out.read_text().strip())
            assert data["session_id"] == "s1"
        finally:
            kafka_consumer.EVENTS_DIR = original

    def test_write_event_appends(self, tmp_path: Path) -> None:
        from app.ml import kafka_consumer

        original = kafka_consumer.EVENTS_DIR
        kafka_consumer.EVENTS_DIR = tmp_path
        try:
            kafka_consumer._write_event("matches", {"match_id": "m1"})
            kafka_consumer._write_event("matches", {"match_id": "m2"})
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            lines = (tmp_path / "matches" / f"{today}.jsonl").read_text().splitlines()
            assert len(lines) == 2
        finally:
            kafka_consumer.EVENTS_DIR = original

    def test_enrich_session_without_anomaly_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ANOMALY_ENRICH=0, enriched event has None scores but correct structure."""
        from app.ml import kafka_consumer

        monkeypatch.setattr(kafka_consumer, "ENRICH_ANOMALY", False)
        event = {
            "session_id": "s1",
            "time_elapsed_ms": 300_000,
            "cells_filled": 45,
            "errors_count": 2,
            "hints_used": 1,
            "difficulty": "medium",
        }
        enriched = kafka_consumer._enrich_session(event)
        assert enriched["anomaly_score"] is None
        assert enriched["is_anomalous"] is None
        assert "enriched_at" in enriched

    def test_enrich_session_with_mocked_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ml import kafka_consumer

        monkeypatch.setattr(kafka_consumer, "ENRICH_ANOMALY", True)

        class _FakeService:
            def score(self, **_: Any) -> dict[str, Any]:
                return {"anomaly_score": 0.3, "reconstruction_error": 0.02, "is_anomalous": False}

        import app.services.anomaly_service as as_mod
        monkeypatch.setattr(as_mod, "anomaly_service", _FakeService())

        event = {
            "session_id": "s2",
            "time_elapsed_ms": 180_000,
            "cells_filled": 40,
            "errors_count": 1,
            "hints_used": 0,
            "difficulty": "easy",
        }
        enriched = kafka_consumer._enrich_session(event)
        assert enriched["anomaly_score"] == pytest.approx(0.3)
        assert enriched["is_anomalous"] is False

    def test_handle_session_invalid_json_does_not_raise(self, tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ml import kafka_consumer

        monkeypatch.setattr(kafka_consumer, "EVENTS_DIR", tmp_path)
        monkeypatch.setattr(kafka_consumer, "ENRICH_ANOMALY", False)
        # Should not raise even with garbage bytes.
        kafka_consumer._handle_session(b"not-json{{{")

    def test_handle_match_writes_consumed_at(self, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ml import kafka_consumer

        monkeypatch.setattr(kafka_consumer, "EVENTS_DIR", tmp_path)
        raw = json.dumps({"match_id": "m99", "winner_id": "u1", "elo_delta": 12}).encode()
        kafka_consumer._handle_match(raw)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = (tmp_path / "matches" / f"{today}.jsonl").read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "consumed_at" in data


# ─── CompetitiveDuckdbService ─────────────────────────────────────────────────


class TestCompetitiveDuckdbService:
    """Uses a tmp file DuckDB seeded with fixture data."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> str:
        path = str(tmp_path / "competitive.duckdb")
        conn = _make_db(path)
        _seed_match(conn, "m1", winner_id="u1", loser_id="u2", elo_delta=16)
        _seed_match(conn, "m2", winner_id="u3", loser_id="u1", elo_delta=12)
        _seed_session(conn, "s1", is_anomalous=False)
        _seed_session(conn, "s2", is_anomalous=True)

        # Populate aggregation tables.
        conn.execute("""
            INSERT INTO elo_trends VALUES
            ('2026-03-13','u1',2,1,1,1200,1204,4),
            ('2026-03-13','u2',1,0,1,1200,1184,-16),
            ('2026-03-13','u3',1,1,0,1200,1212,12)
        """)
        conn.execute("""
            INSERT INTO leaderboard_snapshots VALUES
            ('2026-03-13',1,'u3',1212,1,0),
            ('2026-03-13',2,'u1',1204,1,1),
            ('2026-03-13',3,'u2',1184,0,1)
        """)
        conn.execute("""
            INSERT INTO match_stats_daily VALUES
            ('2026-03-13',2,180000.0,14.0,'{"medium":2}','{"completion":2}')
        """)
        conn.execute("""
            INSERT INTO anomaly_reports_daily VALUES
            ('2026-03-13',2,1,0.5,0.3)
        """)
        conn.close()
        return path

    @pytest.fixture(autouse=True)
    def patch_db_path(self, db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.competitive_duckdb_service as svc
        monkeypatch.setattr(svc, "COMPETITIVE_DUCKDB_PATH", db_path)

    def test_get_elo_trend_returns_list(self) -> None:
        from app.services.competitive_duckdb_service import get_elo_trend
        rows = get_elo_trend("u1", days=30)
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_get_elo_trend_keys(self) -> None:
        from app.services.competitive_duckdb_service import get_elo_trend
        row = get_elo_trend("u1", days=30)[0]
        for key in ("date", "matches_played", "wins", "losses", "elo_start", "elo_end", "elo_delta"):
            assert key in row

    def test_get_elo_trend_unknown_user_returns_empty(self) -> None:
        from app.services.competitive_duckdb_service import get_elo_trend
        rows = get_elo_trend("nobody", days=30)
        assert rows == []

    def test_get_leaderboard_snapshot_returns_list(self) -> None:
        from app.services.competitive_duckdb_service import get_leaderboard_snapshot
        rows = get_leaderboard_snapshot()
        assert isinstance(rows, list)
        assert len(rows) == 3

    def test_leaderboard_snapshot_rank_ordering(self) -> None:
        from app.services.competitive_duckdb_service import get_leaderboard_snapshot
        rows = get_leaderboard_snapshot()
        ranks = [r["rank"] for r in rows]
        assert ranks == sorted(ranks)

    def test_leaderboard_snapshot_win_rate(self) -> None:
        from app.services.competitive_duckdb_service import get_leaderboard_snapshot
        rows = get_leaderboard_snapshot()
        # u3: 1W 0L → winRate = 1.0
        u3 = next(r for r in rows if r["user_id"] == "u3")
        assert u3["win_rate"] == pytest.approx(1.0)

    def test_get_match_stats_returns_list(self) -> None:
        from app.services.competitive_duckdb_service import get_match_stats
        rows = get_match_stats(days=30)
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_match_stats_keys(self) -> None:
        from app.services.competitive_duckdb_service import get_match_stats
        row = get_match_stats(days=30)[0]
        for key in ("date", "total_matches", "avg_duration_ms", "avg_elo_delta",
                    "difficulty_breakdown", "end_reason_breakdown"):
            assert key in row

    def test_get_anomaly_report_returns_list(self) -> None:
        from app.services.competitive_duckdb_service import get_anomaly_report
        rows = get_anomaly_report(days=30)
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_anomaly_report_flag_rate(self) -> None:
        from app.services.competitive_duckdb_service import get_anomaly_report
        row = get_anomaly_report(days=30)[0]
        assert row["flag_rate"] == pytest.approx(0.5)

    def test_get_competitive_summary_available(self) -> None:
        from app.services.competitive_duckdb_service import get_competitive_summary
        result = get_competitive_summary()
        assert result["available"] is True
        assert "top10" in result
        assert "recent_matches_7d" in result

    def test_get_competitive_summary_not_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.competitive_duckdb_service as svc
        monkeypatch.setattr(svc, "COMPETITIVE_DUCKDB_PATH", "/nonexistent/path.duckdb")
        result = svc.get_competitive_summary()
        assert result["available"] is False
        assert "message" in result


# ─── FastAPI endpoints ────────────────────────────────────────────────────────


class TestCompetitiveEndpoints:
    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> str:
        path = str(tmp_path / "competitive.duckdb")
        conn = _make_db(path)
        _seed_session(conn, "s1", is_anomalous=False)
        conn.execute("""
            INSERT INTO elo_trends VALUES
            ('2026-03-13','u1',1,1,0,1200,1216,16)
        """)
        conn.execute("""
            INSERT INTO leaderboard_snapshots VALUES
            ('2026-03-13',1,'u1',1216,1,0)
        """)
        conn.execute("""
            INSERT INTO match_stats_daily VALUES
            ('2026-03-13',1,180000.0,16.0,'{"medium":1}','{"completion":1}')
        """)
        conn.execute("""
            INSERT INTO anomaly_reports_daily VALUES
            ('2026-03-13',1,0,0.0,0.1)
        """)
        conn.close()
        return path

    @pytest.fixture()
    def client(self, db_path: str, monkeypatch: pytest.MonkeyPatch):
        import app.services.competitive_duckdb_service as svc
        monkeypatch.setattr(svc, "COMPETITIVE_DUCKDB_PATH", db_path)
        from starlette.testclient import TestClient
        from app.main import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    def test_summary_returns_200(self, client) -> None:
        resp = client.get("/api/v1/competitive/summary")
        assert resp.status_code == 200

    def test_summary_available_field(self, client) -> None:
        body = client.get("/api/v1/competitive/summary").json()
        assert "available" in body

    def test_leaderboard_returns_200(self, client) -> None:
        resp = client.get("/api/v1/competitive/leaderboard")
        assert resp.status_code == 200

    def test_leaderboard_is_list(self, client) -> None:
        body = client.get("/api/v1/competitive/leaderboard").json()
        assert isinstance(body, list)

    def test_leaderboard_limit_param(self, client) -> None:
        resp = client.get("/api/v1/competitive/leaderboard?limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) <= 1

    def test_elo_trend_returns_200(self, client) -> None:
        resp = client.get("/api/v1/competitive/elo-trend/u1")
        assert resp.status_code == 200

    def test_elo_trend_unknown_user_returns_empty_list(self, client) -> None:
        body = client.get("/api/v1/competitive/elo-trend/nobody").json()
        assert body == []

    def test_match_stats_returns_200(self, client) -> None:
        resp = client.get("/api/v1/competitive/match-stats")
        assert resp.status_code == 200

    def test_match_stats_is_list(self, client) -> None:
        body = client.get("/api/v1/competitive/match-stats").json()
        assert isinstance(body, list)

    def test_anomaly_report_returns_200(self, client) -> None:
        resp = client.get("/api/v1/competitive/anomaly-report")
        assert resp.status_code == 200

    def test_anomaly_report_is_list(self, client) -> None:
        body = client.get("/api/v1/competitive/anomaly-report").json()
        assert isinstance(body, list)

    def test_leaderboard_503_when_no_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.services.competitive_duckdb_service as svc
        monkeypatch.setattr(svc, "COMPETITIVE_DUCKDB_PATH", "/no/such/file.duckdb")
        from starlette.testclient import TestClient
        from app.main import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/api/v1/competitive/leaderboard")
        assert resp.status_code == 503


# ─── Airflow DAG task functions ───────────────────────────────────────────────


class TestAirflowDagTasks:
    """Test each task callable in isolation with a tmp DuckDB and tmp JSONL files."""

    @pytest.fixture()
    def ctx(self, tmp_path: Path) -> dict:
        """Airflow task execution context mock."""
        from datetime import timezone
        return {
            "data_interval_start": datetime(2026, 3, 13, 0, 0, 0, tzinfo=timezone.utc),
        }

    @pytest.fixture()
    def dag_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
        """Set module-level paths for the DAG module."""
        import airflow.dags.competitive_analytics_dag as dag_mod

        db_path = str(tmp_path / "competitive.duckdb")
        monkeypatch.setattr(dag_mod, "DUCKDB_PATH", db_path)
        monkeypatch.setattr(dag_mod, "EVENTS_DIR", tmp_path)

        # Pre-create schema.
        dag_mod.ensure_schema(data_interval_start=datetime(2026, 3, 13, tzinfo=timezone.utc))

        return {"db_path": db_path, "events_dir": tmp_path, "mod": dag_mod}

    def _write_jsonl(self, events_dir: Path, subdir: str, target_date: str,
                     events: list[dict]) -> None:
        out = events_dir / subdir / f"{target_date}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")

    def test_ensure_schema_creates_tables(self, dag_env: dict, ctx: dict) -> None:
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        conn.close()
        assert "competitive_matches" in tables
        assert "leaderboard_snapshots" in tables

    def test_load_match_events_inserts_rows(self, dag_env: dict, ctx: dict) -> None:
        mod = dag_env["mod"]
        self._write_jsonl(
            dag_env["events_dir"], "matches", "2026-03-13",
            [{"match_id": "m1", "room_id": "r1", "winner_id": "u1",
              "loser_id": "u2", "winner_elo_before": 1200, "winner_elo_after": 1216,
              "loser_elo_before": 1200, "loser_elo_after": 1184,
              "elo_delta": 16, "difficulty": "medium", "end_reason": "completion",
              "duration_ms": 180_000, "completed_at": "2026-03-13 12:00:00",
              "consumed_at": "2026-03-13 12:00:01"}],
        )
        mod.load_match_events(**ctx)
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM competitive_matches").fetchone()[0]
        conn.close()
        assert count == 1

    def test_load_session_events_inserts_rows(self, dag_env: dict, ctx: dict) -> None:
        mod = dag_env["mod"]
        self._write_jsonl(
            dag_env["events_dir"], "sessions", "2026-03-13",
            [{"session_id": "s1", "user_id": "u1", "puzzle_id": "p1",
              "difficulty": "medium", "time_elapsed_ms": 300_000,
              "score": 1000, "hints_used": 1, "errors_count": 2,
              "completed_at": "2026-03-13 10:00:00",
              "anomaly_score": 0.1, "reconstruction_error": 0.02,
              "is_anomalous": False, "enriched_at": "2026-03-13 10:00:01"}],
        )
        mod.load_session_events(**ctx)
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM enriched_sessions").fetchone()[0]
        conn.close()
        assert count == 1

    def test_load_match_events_idempotent(self, dag_env: dict, ctx: dict) -> None:
        mod = dag_env["mod"]
        match = {"match_id": "m1", "room_id": "r1", "winner_id": "u1",
                 "loser_id": "u2", "winner_elo_before": 1200, "winner_elo_after": 1216,
                 "loser_elo_before": 1200, "loser_elo_after": 1184,
                 "elo_delta": 16, "difficulty": "medium", "end_reason": "completion",
                 "duration_ms": 180_000, "completed_at": "2026-03-13 12:00:00",
                 "consumed_at": "2026-03-13 12:00:01"}
        self._write_jsonl(dag_env["events_dir"], "matches", "2026-03-13", [match])
        mod.load_match_events(**ctx)
        mod.load_match_events(**ctx)  # second run — idempotent via INSERT OR IGNORE
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM competitive_matches").fetchone()[0]
        conn.close()
        assert count == 1

    def test_compute_match_stats_no_events_skips(self, dag_env: dict, ctx: dict) -> None:
        mod = dag_env["mod"]
        mod.compute_match_stats(**ctx)  # should not raise even with 0 rows
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM match_stats_daily").fetchone()[0]
        conn.close()
        assert count == 0

    def test_compute_anomaly_report_no_sessions_skips(self, dag_env: dict, ctx: dict) -> None:
        mod = dag_env["mod"]
        mod.compute_anomaly_report(**ctx)
        conn = duckdb.connect(dag_env["db_path"], read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM anomaly_reports_daily").fetchone()[0]
        conn.close()
        assert count == 0

    def test_full_pipeline(self, dag_env: dict, ctx: dict) -> None:
        """Integration: load events → compute all aggregations → verify output."""
        mod = dag_env["mod"]
        # Seed match events.
        self._write_jsonl(
            dag_env["events_dir"], "matches", "2026-03-13",
            [
                {"match_id": "m1", "room_id": "r1", "winner_id": "u1",
                 "loser_id": "u2", "winner_elo_before": 1200, "winner_elo_after": 1216,
                 "loser_elo_before": 1200, "loser_elo_after": 1184,
                 "elo_delta": 16, "difficulty": "medium", "end_reason": "completion",
                 "duration_ms": 120_000, "completed_at": "2026-03-13 11:00:00",
                 "consumed_at": "2026-03-13 11:00:01"},
                {"match_id": "m2", "room_id": "r2", "winner_id": "u3",
                 "loser_id": "u1", "winner_elo_before": 1300, "winner_elo_after": 1312,
                 "loser_elo_before": 1216, "loser_elo_after": 1204,
                 "elo_delta": 12, "difficulty": "hard", "end_reason": "completion",
                 "duration_ms": 240_000, "completed_at": "2026-03-13 15:00:00",
                 "consumed_at": "2026-03-13 15:00:01"},
            ],
        )
        # Seed session events.
        self._write_jsonl(
            dag_env["events_dir"], "sessions", "2026-03-13",
            [
                {"session_id": "s1", "user_id": "u1", "puzzle_id": "p1",
                 "difficulty": "medium", "time_elapsed_ms": 300_000,
                 "score": 1000, "hints_used": 0, "errors_count": 0,
                 "completed_at": "2026-03-13 10:00:00",
                 "anomaly_score": 0.2, "reconstruction_error": 0.01,
                 "is_anomalous": False, "enriched_at": "2026-03-13 10:00:02"},
                {"session_id": "s2", "user_id": "bot-9", "puzzle_id": "p2",
                 "difficulty": "hard", "time_elapsed_ms": 4_000,
                 "score": 9999, "hints_used": 0, "errors_count": 0,
                 "completed_at": "2026-03-13 10:05:00",
                 "anomaly_score": 2.8, "reconstruction_error": 0.9,
                 "is_anomalous": True, "enriched_at": "2026-03-13 10:05:02"},
            ],
        )

        mod.load_match_events(**ctx)
        mod.load_session_events(**ctx)
        mod.compute_elo_trends(**ctx)
        mod.snapshot_leaderboard(**ctx)
        mod.compute_match_stats(**ctx)
        mod.compute_anomaly_report(**ctx)

        conn = duckdb.connect(dag_env["db_path"], read_only=True)

        # Match stats
        ms = conn.execute("SELECT total_matches, avg_elo_delta FROM match_stats_daily").fetchone()
        assert ms[0] == 2
        assert ms[1] == pytest.approx(14.0)

        # Anomaly report: 1 of 2 sessions flagged
        ar = conn.execute(
            "SELECT flagged_count, flag_rate FROM anomaly_reports_daily"
        ).fetchone()
        assert ar[0] == 1
        assert ar[1] == pytest.approx(0.5)

        # Leaderboard snapshot: u3 should rank 1st (highest elo after his match)
        top = conn.execute(
            "SELECT user_id FROM leaderboard_snapshots ORDER BY rank LIMIT 1"
        ).fetchone()
        assert top[0] == "u3"

        conn.close()
