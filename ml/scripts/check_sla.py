"""
check_sla.py — Verify ML model performance against SLA thresholds.

Trains each model on a small synthetic dataset and evaluates it.  Designed
to run fast (<5 min) in CI by using n_samples=500 and disabling HPO.

PyTorch models (digit-scanner, gan-generator) require --full to run; they are
skipped by default to keep CI runtimes reasonable.

Exit codes
----------
  0  all checked models pass all thresholds
  1  one or more models failed an SLA threshold
  2  partial — some models could not be evaluated (import/train error)

Usage
-----
  # Fast check — sklearn models only (CI default)
  python ml/scripts/check_sla.py

  # Full check — includes PyTorch models (slow, run in nightly)
  python ml/scripts/check_sla.py --full

  # Override samples for a quicker smoke-test
  python ml/scripts/check_sla.py --n-samples 200

  # JSON output for machine consumption
  python ml/scripts/check_sla.py --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("check_sla")

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ml-service"))

# ── SLA definitions ───────────────────────────────────────────────────────────
# Each entry: (model_id, metric_name, threshold, comparison, is_pytorch)
#   comparison: "gte" (metric >= threshold) or "lte" (metric <= threshold)

SLA_TABLE: list[tuple[str, str, float, str, bool]] = [
    ("difficulty-classifier", "test_accuracy",    0.85, "gte", False),
    ("difficulty-classifier", "test_f1_macro",    0.82, "gte", False),
    ("adaptive-regression",   "test_rmse",        0.30, "lte", False),
    ("adaptive-regression",   "test_r2",          0.75, "gte", False),
    ("skill-clustering",      "silhouette_score", 0.40, "gte", False),
    ("churn-predictor",       "test_auc_roc",     0.75, "gte", False),
    ("churn-predictor",       "test_f1",          0.65, "gte", False),
    # PyTorch models — only checked with --full
    ("digit-scanner",         "best_val_accuracy", 0.95, "gte", True),
    ("gan-generator",         "best_g_loss",       1.0,  "lte", True),
]

# ── Training entry points ──────────────────────────────────────────────────────

def _check_classifier(n_samples: int, n_trials: int) -> dict:
    from app.ml.train_classifier import train_and_save
    return train_and_save(n_samples=n_samples, n_trials=n_trials)


def _check_regression(n_samples: int, n_trials: int) -> dict:
    from app.ml.train_regression import train_and_save
    return train_and_save(n_samples=n_samples, n_trials=n_trials)


def _check_clustering(n_samples: int, **_) -> dict:
    from app.ml.train_clustering import train_and_save
    return train_and_save(n_samples=n_samples)


def _check_churn(n_samples: int, n_trials: int) -> dict:
    from app.ml.train_churn import train_and_save
    return train_and_save(n_samples=n_samples, n_trials=n_trials)


def _check_scanner(n_samples: int, **_) -> dict:
    from app.ml.train_scanner import train_and_save
    samples_per_class = max(50, n_samples // 10)
    return train_and_save(samples_per_class=samples_per_class)


def _check_gan(**_) -> dict:
    from app.ml.train_gan import train_and_save
    return train_and_save(epochs=10)   # minimal for CI


TRAINERS: dict[str, object] = {
    "difficulty-classifier": _check_classifier,
    "adaptive-regression":   _check_regression,
    "skill-clustering":      _check_clustering,
    "churn-predictor":       _check_churn,
    "digit-scanner":         _check_scanner,
    "gan-generator":         _check_gan,
}

# ── Evaluation logic ───────────────────────────────────────────────────────────

def evaluate_model(
    model_id: str,
    n_samples: int,
    n_trials: int,
) -> dict:
    """
    Train and evaluate one model.  Returns a result dict:
      {model_id, metrics, status, error, elapsed_s}
    """
    trainer = TRAINERS[model_id]
    t0 = time.time()
    try:
        metrics = trainer(n_samples=n_samples, n_trials=n_trials)
        return {
            "model_id": model_id,
            "metrics":  metrics,
            "status":   "evaluated",
            "error":    None,
            "elapsed_s": round(time.time() - t0, 1),
        }
    except Exception as exc:
        return {
            "model_id": model_id,
            "metrics":  {},
            "status":   "error",
            "error":    str(exc),
            "elapsed_s": round(time.time() - t0, 1),
        }


def check_slas(
    results: list[dict],
    full: bool,
) -> list[dict]:
    """
    Compare each model's metrics against SLA_TABLE.

    Returns a list of finding dicts:
      {model_id, metric, value, threshold, comparison, passed, skipped}
    """
    # Index results by model_id
    result_map = {r["model_id"]: r for r in results}
    findings = []

    for model_id, metric, threshold, cmp, is_pytorch in SLA_TABLE:
        if is_pytorch and not full:
            findings.append({
                "model_id":   model_id,
                "metric":     metric,
                "value":      None,
                "threshold":  threshold,
                "comparison": cmp,
                "passed":     True,
                "skipped":    True,
                "reason":     "pytorch model — use --full to check",
            })
            continue

        result = result_map.get(model_id)
        if result is None or result["status"] == "error":
            findings.append({
                "model_id":   model_id,
                "metric":     metric,
                "value":      None,
                "threshold":  threshold,
                "comparison": cmp,
                "passed":     False,
                "skipped":    False,
                "reason":     result["error"] if result else "not evaluated",
            })
            continue

        value = result["metrics"].get(metric)
        if value is None:
            findings.append({
                "model_id":   model_id,
                "metric":     metric,
                "value":      None,
                "threshold":  threshold,
                "comparison": cmp,
                "passed":     False,
                "skipped":    False,
                "reason":     f"metric '{metric}' missing from trainer output",
            })
            continue

        if cmp == "gte":
            passed = value >= threshold
        else:  # lte
            passed = value <= threshold

        findings.append({
            "model_id":   model_id,
            "metric":     metric,
            "value":      round(float(value), 4),
            "threshold":  threshold,
            "comparison": cmp,
            "passed":     passed,
            "skipped":    False,
            "reason":     None,
        })

    return findings


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Check ML model performance SLAs.")
    parser.add_argument("--n-samples", type=int, default=500,
                        help="Training samples per model (default: 500)")
    parser.add_argument("--n-trials",  type=int, default=1,
                        help="Optuna HPO trials (default: 1 — disabled)")
    parser.add_argument("--full",      action="store_true",
                        help="Include PyTorch models (slow)")
    parser.add_argument("--json",      action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    # Determine which models to run
    models_to_run = list(TRAINERS.keys())
    if not args.full:
        pytorch_models = {"digit-scanner", "gan-generator"}
        models_to_run  = [m for m in models_to_run if m not in pytorch_models]

    if not args.json:
        log.info(f"Checking {len(models_to_run)} model(s) "
                 f"(n_samples={args.n_samples}, n_trials={args.n_trials})")
        log.info("")

    # Train + evaluate all models
    eval_results = []
    for model_id in models_to_run:
        if not args.json:
            log.info(f"  Training {model_id} …")
        r = evaluate_model(model_id, args.n_samples, args.n_trials)
        eval_results.append(r)
        if not args.json:
            if r["status"] == "error":
                log.warning(f"  ERROR: {r['error']}")
            else:
                log.info(f"  metrics={r['metrics']}  [{r['elapsed_s']}s]")
        log.info("")

    # Check SLAs
    findings = check_slas(eval_results, args.full)

    # Count pass/fail/skip
    failed  = [f for f in findings if not f["passed"] and not f["skipped"]]
    passed  = [f for f in findings if f["passed"]  and not f["skipped"]]
    skipped = [f for f in findings if f["skipped"]]

    if args.json:
        print(json.dumps({
            "summary": {
                "passed":  len(passed),
                "failed":  len(failed),
                "skipped": len(skipped),
            },
            "findings": findings,
        }, indent=2))
    else:
        log.info("── SLA Results ───────────────────────────────────────────")
        for f in findings:
            if f["skipped"]:
                log.info(f"  SKIP  {f['model_id']}.{f['metric']}  ({f['reason']})")
            elif f["passed"]:
                cmp_str = ">=" if f["comparison"] == "gte" else "<="
                log.info(f"  PASS  {f['model_id']}.{f['metric']} "
                         f"{f['value']} {cmp_str} {f['threshold']}")
            else:
                cmp_str = ">=" if f["comparison"] == "gte" else "<="
                val     = f['value'] if f['value'] is not None else "N/A"
                log.error(f"  FAIL  {f['model_id']}.{f['metric']} "
                          f"{val} {cmp_str} {f['threshold']}  ← {f.get('reason','below threshold')}")

        log.info("")
        log.info(f"Summary: {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")

    # Exit codes
    has_error = any(r["status"] == "error" for r in eval_results)
    if failed:
        return 1
    if has_error:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
