"""
test_moderate.py — pytest suite for the toxicity moderation service and API.

Tests are grouped:
  - ToxicityService keyword fallback (no model required)
  - ToxicityService edge cases
  - FastAPI endpoint via httpx Client
"""

from __future__ import annotations

import pytest


# ─── ToxicityService (keyword fallback) ───────────────────────────────────────

class TestToxicityServiceKeyword:
    """Force keyword fallback by patching _ensure_loaded to be a no-op."""

    @pytest.fixture(autouse=True)
    def force_keyword_fallback(self, monkeypatch):
        from app.services.toxicity_service import ToxicityService
        # Ensure pipeline stays None so keyword path is exercised.
        monkeypatch.setattr(ToxicityService, "_ensure_loaded", lambda self: None)

    def test_clean_message_returns_not_toxic(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("Good game, well played!")
        assert not result["is_toxic"]
        assert result["category"] == "clean"
        assert 0.0 <= result["confidence"] <= 1.0

    def test_obvious_toxic_message(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("You are such an idiot!")
        assert result["is_toxic"]
        assert result["confidence"] > 0.0

    def test_severe_toxic_category(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("kill yourself")
        assert result["is_toxic"]
        assert result["category"] == "severe_toxic"

    def test_threat_category(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("I will kill you")
        assert result["is_toxic"]
        assert result["category"] == "threat"

    def test_empty_string_is_clean(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("")
        assert not result["is_toxic"]
        assert result["category"] == "clean"

    def test_whitespace_only_is_clean(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("   ")
        assert not result["is_toxic"]

    def test_long_text_truncated_and_processed(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        long_text = "Hello " * 200  # well over 512 chars
        result = svc.predict(long_text)
        assert isinstance(result["is_toxic"], bool)

    def test_result_has_required_keys(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("Nice move!")
        assert "is_toxic" in result
        assert "confidence" in result
        assert "category" in result

    def test_confidence_is_between_zero_and_one(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        for text in ["hello", "you idiot", "kill yourself", "great puzzle"]:
            result = svc.predict(text)
            assert 0.0 <= result["confidence"] <= 1.0, (
                f"confidence out of range for: {text!r}"
            )

    def test_predict_does_not_raise_on_unicode(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        # Should not raise on emoji / unicode
        result = svc.predict("👍 great game! 🎉")
        assert isinstance(result["is_toxic"], bool)

    def test_clean_category_for_non_toxic(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("Well done!")
        assert result["category"] == "clean"

    def test_toxic_category_not_clean(self):
        from app.services.toxicity_service import ToxicityService
        svc = ToxicityService()
        result = svc.predict("you stupid moron")
        assert result["category"] != "clean"


# ─── FastAPI Endpoint ──────────────────────────────────────────────────────────

class TestModerateEndpoint:
    """Integration tests via httpx Client — keyword fallback forced."""

    @pytest.fixture()
    def client(self, monkeypatch):
        from app.services.toxicity_service import ToxicityService
        monkeypatch.setattr(ToxicityService, "_ensure_loaded", lambda self: None)

        from httpx import Client
        from app.main import create_app
        app = create_app()
        with Client(app=app, base_url="http://test") as c:
            yield c

    def test_clean_message_200(self, client):
        resp = client.post("/api/v1/moderate", json={"text": "Nice move!"})
        assert resp.status_code == 200
        body = resp.json()
        assert "is_toxic" in body
        assert "confidence" in body
        assert "category" in body

    def test_clean_message_not_toxic(self, client):
        resp = client.post("/api/v1/moderate", json={"text": "Good game!"})
        body = resp.json()
        assert not body["is_toxic"]
        assert body["category"] == "clean"

    def test_toxic_message_flagged(self, client):
        resp = client.post("/api/v1/moderate", json={"text": "You are an idiot"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_toxic"]

    def test_empty_text_returns_422(self, client):
        resp = client.post("/api/v1/moderate", json={"text": ""})
        assert resp.status_code == 422

    def test_missing_text_field_returns_422(self, client):
        resp = client.post("/api/v1/moderate", json={})
        assert resp.status_code == 422

    def test_text_too_long_returns_422(self, client):
        resp = client.post("/api/v1/moderate", json={"text": "x" * 2001})
        assert resp.status_code == 422

    def test_whitespace_text_returns_422(self, client):
        # strip_text validator + min_length=1 should reject whitespace-only
        resp = client.post("/api/v1/moderate", json={"text": "   "})
        assert resp.status_code == 422

    def test_severe_toxic_category_returned(self, client):
        resp = client.post("/api/v1/moderate", json={"text": "kill yourself"})
        body = resp.json()
        assert body["is_toxic"]
        assert body["category"] == "severe_toxic"

    def test_confidence_range(self, client):
        for text in ["hello", "you idiot", "great game"]:
            resp = client.post("/api/v1/moderate", json={"text": text})
            body = resp.json()
            assert 0.0 <= body["confidence"] <= 1.0
