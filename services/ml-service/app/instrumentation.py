"""
instrumentation.py — OpenTelemetry + Sentry initialisation for ml-service.

Call configure() once at application startup (before FastAPI is created).

Environment variables:
  OTEL_SERVICE_NAME              ml-service (default)
  OTEL_EXPORTER_OTLP_ENDPOINT    http://otel-collector:4318 (default)
  OTEL_TRACES_SAMPLER            parentbased_traceidratio (default)
  OTEL_TRACES_SAMPLER_ARG        1.0 (100% in dev; reduce to 0.05 in prod)
  SENTRY_DSN                     (optional)
  DEPLOY_ENV                     production | staging | development (default)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("instrumentation")

_SERVICE_NAME  = os.getenv("OTEL_SERVICE_NAME", "ml-service")
_OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
_DEPLOY_ENV    = os.getenv("DEPLOY_ENV", "development")
_SAMPLE_RATE   = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))

_configured = False


def configure() -> None:
    """
    Configure OpenTelemetry SDK and Sentry.
    Safe to call multiple times — only configures once.
    """
    global _configured
    if _configured:
        return
    _configured = True

    _init_otel()
    _init_sentry()


def _init_otel() -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

        resource = Resource.create({
            SERVICE_NAME:    _SERVICE_NAME,
            SERVICE_VERSION: os.getenv("APP_VERSION", "0.0.1"),
            "deployment.environment": _DEPLOY_ENV,
        })

        provider = TracerProvider(
            resource=resource,
            sampler=ParentBasedTraceIdRatio(_SAMPLE_RATE),
        )

        exporter = OTLPSpanExporter(
            endpoint=f"{_OTEL_ENDPOINT}/v1/traces",
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument HTTP clients and DB drivers
        RequestsInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()

        # FastAPI instrumentor is applied in main.py via FastAPIInstrumentor().instrument_app(app)
        # (must happen after app is created)

        logger.info(
            f"[instrumentation] OTel SDK configured — "
            f"service={_SERVICE_NAME} endpoint={_OTEL_ENDPOINT} sample_rate={_SAMPLE_RATE}"
        )

    except ImportError as exc:
        logger.warning(
            f"[instrumentation] opentelemetry packages not fully installed: {exc}. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-psycopg2"
        )


def _init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        import logging as _logging

        sentry_sdk.init(
            dsn=dsn,
            environment=_DEPLOY_ENV,
            traces_sample_rate=0.05 if _DEPLOY_ENV == "production" else 1.0,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(
                    level=_logging.WARNING,
                    event_level=_logging.ERROR,
                ),
            ],
        )
        logger.info("[instrumentation] Sentry SDK initialised")
    except ImportError:
        logger.warning(
            "[instrumentation] sentry-sdk not installed — Sentry disabled. "
            "Install with: pip install sentry-sdk[fastapi]"
        )


def instrument_fastapi(app) -> None:
    """
    Apply FastAPI OTel instrumentation to an existing FastAPI app instance.
    Call this after configure() and after the FastAPI app is constructed.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/health,/metrics",
        )
        logger.info("[instrumentation] FastAPI instrumentor applied")
    except ImportError:
        pass
