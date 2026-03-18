# ML Performance SLAs

This document defines the minimum acceptable performance thresholds for all
six production ML models in Sudoku Ultra.  Thresholds apply to the **Production**
model version registered in the MLflow Model Registry.

SLAs are enforced automatically:
- **CI gate** (`ml-sla` job in `.github/workflows/ci.yml`) — runs on every push,
  evaluates sklearn models on n=500 synthetic samples.
- **Nightly drift check** (`model-drift` job in `.github/workflows/nightly.yml`) —
  monitors PSI on live inference data; alerts on drift > 0.1, fails at > 0.2.
- **Retraining DAGs** — each retrain DAG refuses to promote a new model to
  Production unless it meets the thresholds below.

---

## Model SLAs

### 1. difficulty-classifier

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `test_accuracy` | ≥ 0.88 | Held-out test split (20%) |
| `test_f1_macro` | ≥ 0.85 | Held-out test split (20%) |

**CI gate**: `test_accuracy ≥ 0.85`, `test_f1_macro ≥ 0.82` (relaxed for n=500 synthetic data).
**Registry gate**: Full thresholds applied by `retrain_classifier` DAG before promotion.

**Breach protocol**: If accuracy drops below 0.80 in production monitoring, the
`retrain_classifier` DAG is triggered immediately and the Slack `#ml-alerts`
channel is notified.

---

### 2. adaptive-regression

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `test_rmse` | ≤ 0.25 | Held-out test split (20%) |
| `test_r2` | ≥ 0.80 | Held-out test split (20%) |

**CI gate**: `test_rmse ≤ 0.30`, `test_r2 ≥ 0.75` (relaxed for n=500).
**Registry gate**: Full thresholds applied by `retrain_regression` DAG.

---

### 3. digit-scanner

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `best_val_accuracy` | ≥ 0.97 | Validation set (synthetic MNIST-style digits) |

**CI gate**: Skipped by default (PyTorch, slow). Use `--full` flag in `check_sla.py` or rely on nightly run.
**Registry gate**: Full threshold applied by `retrain_scanner` DAG.

**Note**: The scanner is evaluated on synthetic digit images.  Real-world scanning
accuracy may vary with image quality; monitor the `/api/v1/scan` error rate in
Grafana as a proxy.

---

### 4. skill-clustering

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `silhouette_score` | ≥ 0.50 | Full training set |

**CI gate**: `silhouette_score ≥ 0.40` (relaxed for n=500).
**Registry gate**: Full threshold applied by `retrain_clustering` DAG.

**Note**: Silhouette score is sensitive to the number of clusters (k=8 fixed).
If the score is consistently at the boundary, consider re-evaluating k via the
elbow method in the next quarterly model review.

---

### 5. churn-predictor

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `test_auc_roc` | ≥ 0.80 | Held-out test split (20%) |
| `test_f1` | ≥ 0.72 | Held-out test split (20%) |

**CI gate**: `test_auc_roc ≥ 0.75`, `test_f1 ≥ 0.65` (relaxed for n=500).
**Registry gate**: Full thresholds applied by `retrain_churn` DAG.

---

### 6. gan-generator

| Metric | Threshold | Measured on |
|--------|-----------|-------------|
| `best_g_loss` | ≤ 0.50 | Best checkpoint over training epochs |
| puzzle validity rate | ≥ 0.95 | 100 generated puzzles, checked by solver |

**CI gate**: Skipped by default (PyTorch + WGAN-GP, slow). Checked in nightly.
**Registry gate**: `best_g_loss ≤ 0.50` applied by `retrain_gan` DAG.

**Note**: Generator loss is a Wasserstein distance estimate and is not directly
comparable across training runs that use different batch sizes or learning rates.
Use the validity rate metric from the nightly evaluation as the primary quality
signal.

---

## SLA Check Tools

### CI (fast, sklearn only)

```bash
# From repo root, with ml-service dependencies installed:
cd services/ml-service
python ../../ml/scripts/check_sla.py --n-samples 500 --n-trials 1
```

### Full check (includes PyTorch, run locally or in nightly)

```bash
cd services/ml-service
python ../../ml/scripts/check_sla.py --full --n-samples 2000 --n-trials 5
```

### JSON output (for programmatic consumption)

```bash
python ../../ml/scripts/check_sla.py --json | jq '.summary'
```

### Check MLflow registry metrics (post-training)

```bash
python ml/scripts/register_models.py --dry-run   # preview what would be registered
```

---

## Breach Response

| Severity | Condition | Action |
|----------|-----------|--------|
| **Warning** | Metric within 10% of threshold | Slack alert; schedule retrain within 48h |
| **Critical** | Metric below threshold | Immediate DAG trigger; page on-call if production traffic affected |
| **Hard failure** | CI `ml-sla` job fails | Block merge; team lead reviews before bypass |

---

## Reviewing SLAs

SLAs should be reviewed:
- After each major data distribution shift (new puzzle sets, new difficulty tiers)
- Quarterly as part of the model health review
- Whenever a model is retrained with a substantially different architecture

To update a threshold, change both this document **and** the corresponding
constant in `ml/scripts/check_sla.py` (`SLA_TABLE`) and the retraining DAG
(`retrain_*.py`, `evaluate_metrics()` function).
