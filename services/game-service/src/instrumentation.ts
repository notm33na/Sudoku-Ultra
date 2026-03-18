/**
 * instrumentation.ts — OpenTelemetry SDK initialisation for game-service.
 *
 * Must be the FIRST import in src/index.ts (before Express, Prisma, etc.)
 * so that auto-instrumentation patches are applied before any module is loaded.
 *
 * Configured via environment variables:
 *   OTEL_SERVICE_NAME          game-service (default)
 *   OTEL_EXPORTER_OTLP_ENDPOINT http://otel-collector:4318 (default)
 *   OTEL_TRACES_SAMPLER        parentbased_traceidratio (default)
 *   OTEL_TRACES_SAMPLER_ARG    1.0 (default — 100% sampling in dev; lower in prod)
 *   SENTRY_DSN                 (optional) Sentry error tracking DSN
 *   NODE_ENV                   production | staging | development
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { Resource } from '@opentelemetry/resources';
import { SEMRESATTRS_SERVICE_NAME, SEMRESATTRS_SERVICE_VERSION, SEMRESATTRS_DEPLOYMENT_ENVIRONMENT } from '@opentelemetry/semantic-conventions';

const SERVICE_NAME    = process.env.OTEL_SERVICE_NAME    ?? 'game-service';
const OTEL_ENDPOINT   = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? 'http://otel-collector:4318';
const DEPLOY_ENV      = process.env.NODE_ENV ?? 'development';
const SERVICE_VERSION = process.env.npm_package_version  ?? '0.0.1';

// ── Sentry (optional) ─────────────────────────────────────────────────────────

function initSentry(): void {
    const dsn = process.env.SENTRY_DSN;
    if (!dsn) return;

    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const Sentry = require('@sentry/node') as typeof import('@sentry/node');
        Sentry.init({
            dsn,
            environment:  DEPLOY_ENV,
            release:      `${SERVICE_NAME}@${SERVICE_VERSION}`,
            tracesSampleRate: DEPLOY_ENV === 'production' ? 0.1 : 1.0,
            // Capture unhandled promise rejections and uncaught exceptions
            integrations: [
                Sentry.captureConsoleIntegration({ levels: ['error', 'warn'] }),
            ],
        });
        console.info('[instrumentation] Sentry initialised');
    } catch {
        console.warn('[instrumentation] @sentry/node not installed — Sentry disabled');
    }
}

// ── OpenTelemetry SDK ─────────────────────────────────────────────────────────

const traceExporter = new OTLPTraceExporter({
    url: `${OTEL_ENDPOINT}/v1/traces`,
});

const metricExporter = new OTLPMetricExporter({
    url: `${OTEL_ENDPOINT}/v1/metrics`,
});

const sdk = new NodeSDK({
    resource: new Resource({
        [SEMRESATTRS_SERVICE_NAME]:           SERVICE_NAME,
        [SEMRESATTRS_SERVICE_VERSION]:        SERVICE_VERSION,
        [SEMRESATTRS_DEPLOYMENT_ENVIRONMENT]: DEPLOY_ENV,
    }),
    traceExporter,
    metricReader: new PeriodicExportingMetricReader({
        exporter: metricExporter,
        exportIntervalMillis: 15_000,
    }),
    instrumentations: [
        getNodeAutoInstrumentations({
            // HTTP: auto-instrument Express routes
            '@opentelemetry/instrumentation-http': {
                ignoreIncomingRequestHook: (req) =>
                    req.url === '/health' || req.url === '/metrics',
            },
            // Prisma ORM — trace DB queries
            '@opentelemetry/instrumentation-prisma': { enabled: true },
            // Disable noisy fs instrumentation
            '@opentelemetry/instrumentation-fs': { enabled: false },
        }),
    ],
});

// ── Startup ───────────────────────────────────────────────────────────────────

try {
    sdk.start();
    initSentry();
    console.info(
        `[instrumentation] OTel SDK started — service=${SERVICE_NAME} env=${DEPLOY_ENV} endpoint=${OTEL_ENDPOINT}`
    );
} catch (err) {
    console.error('[instrumentation] OTel SDK failed to start:', err);
}

// Graceful shutdown: flush spans before process exits
process.on('SIGTERM', () => {
    sdk.shutdown()
        .then(() => console.info('[instrumentation] OTel SDK shut down'))
        .catch((err) => console.error('[instrumentation] OTel shutdown error:', err));
});
