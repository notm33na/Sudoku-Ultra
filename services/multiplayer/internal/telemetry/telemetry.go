// Package telemetry configures OpenTelemetry tracing for the multiplayer service.
//
// Usage:
//
//	shutdown := telemetry.Init(ctx, "multiplayer", "0.1.0")
//	defer shutdown(ctx)
//
// Environment variables:
//
//	OTEL_EXPORTER_OTLP_ENDPOINT  http://otel-collector:4318 (default)
//	OTEL_TRACES_SAMPLER_ARG      1.0  (sample rate 0.0–1.0; default 1.0)
//	DEPLOY_ENV                   production | staging | development
package telemetry

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.uber.org/zap"
)

// Init configures the OTel TracerProvider and returns a shutdown function.
// The caller must invoke shutdown when the process exits.
func Init(ctx context.Context, serviceName, serviceVersion string, log *zap.Logger) func(context.Context) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "http://otel-collector:4318"
	}
	deployEnv := os.Getenv("DEPLOY_ENV")
	if deployEnv == "" {
		deployEnv = "development"
	}
	sampleRate := 1.0
	if v := os.Getenv("OTEL_TRACES_SAMPLER_ARG"); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			sampleRate = f
		}
	}

	// Build OTLP HTTP exporter
	exp, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint(endpoint),
		otlptracehttp.WithURLPath("/v1/traces"),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		log.Warn("OTel OTLP exporter init failed — tracing disabled",
			zap.String("endpoint", endpoint),
			zap.Error(err),
		)
		return func(_ context.Context) {}
	}

	res, _ := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
			semconv.ServiceVersion(serviceVersion),
			attribute.String("deployment.environment", deployEnv),
		),
	)

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp,
			sdktrace.WithBatchTimeout(5*time.Second),
		),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(
			sdktrace.ParentBased(sdktrace.TraceIDRatioBased(sampleRate)),
		),
	)
	otel.SetTracerProvider(tp)

	log.Info("OTel tracing configured",
		zap.String("service", serviceName),
		zap.String("endpoint", endpoint),
		zap.String("env", deployEnv),
		zap.Float64("sample_rate", sampleRate),
	)

	return func(ctx context.Context) {
		shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		if err := tp.Shutdown(shutdownCtx); err != nil {
			log.Error("OTel shutdown error", zap.Error(err))
		}
	}
}

// Tracer returns a named OTel tracer scoped to the given component.
// Example: telemetry.Tracer("hub").Start(ctx, "broadcast")
func Tracer(component string) interface {
	Start(ctx context.Context, spanName string, opts ...interface{}) (context.Context, interface{})
} {
	return otel.Tracer(fmt.Sprintf("sudoku-ultra/multiplayer/%s", component))
}
