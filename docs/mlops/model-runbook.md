# MLOps Model Runbook

This runbook covers all ML models and data pipelines in Sudoku Ultra Phase 4.

---

## Models at a Glance

| Model | Type | Framework | Tracked in | Served by |
|---|---|---|---|---|
| Difficulty Classifier | Gradient Boosting | scikit-learn | MLflow | ml-service |
| GAN Puzzle Generator | WGAN-GP | PyTorch | MLflow | ml-service |
| Puzzle Embeddings | sentence-transformers | HuggingFace | — | ml-service |
| User Preference Embeddings | Aggregated session vectors | numpy | — | ml-service |
| RAG Technique Retriever | `all-MiniLM-L6-v2` | HuggingFace | — | Qdrant |

---

## 1. Difficulty Classifier

### Purpose
Classifies a puzzle grid into difficulty buckets:
`super_easy | easy | medium | hard | super_hard | extreme`.

### Training

```bash
cd services/ml-service
python -m app.ml.train_classifier \
  --data-path data/puzzles.jsonl \
  --mlflow-uri http://localhost:5000 \
  --experiment-name difficulty-classifier
```

### Updating the model in production

1. Train locally or in CI, verify metrics in MLflow.
2. Register the model: `mlflow models register -m runs:/<RUN_ID>/model -n difficulty-classifier`.
3. Promote to `Production` stage via MLflow UI or:
   ```bash
   mlflow models transition-model-stage \
     -m difficulty-classifier -v <VERSION> --stage Production
   ```
4. ml-service loads the model on startup from `MLFLOW_TRACKING_URI`.
   Restart the pod to pick up the new version:
   ```bash
   kubectl -n sudoku-ultra rollout restart deployment/sudoku-ultra-ml-service
   ```

### Monitoring

- **Drift**: Airflow DAG `model_drift_check` runs nightly and logs feature
  distribution KL-divergence to MLflow.
- **Accuracy**: Spot-check with `POST /ml/api/v1/xai/explain` — confidence
  scores below 0.6 indicate the classifier may need retraining.

---

## 2. GAN Puzzle Generator

### Architecture
- Generator: `[latent(64) | difficulty_onehot(5)] → [Linear → BN → ReLU] × 4 → Linear(81×9)`
- Critic: `[81×9 grid] → [Linear → LeakyReLU] × 4 → Linear(1)`
- Training: WGAN-GP, gradient penalty λ=10, n_critic=5

### Training

```bash
cd ml/scripts
python train_gan.py \
  --epochs 200 \
  --batch-size 64 \
  --data-path ../../data/puzzles.jsonl \
  --mlflow-uri http://localhost:5000
```

Training logs FID score, generator loss, and critic loss to MLflow every 10 epochs.

### Acceptance criteria before deploying a new GAN checkpoint

| Metric | Threshold |
|---|---|
| Valid puzzle rate (unique solution) | ≥ 95% |
| FID score vs reference set | ≤ 50 |
| Difficulty accuracy (generated vs target) | ≥ 80% |

### Deploying a new checkpoint

1. Export the checkpoint:
   ```bash
   python -c "
   import mlflow
   mlflow.pytorch.log_model(model, 'gan', registered_model_name='sudoku-gan')
   "
   ```
2. Set `GAN_MODEL_URI` env var in `values.prod.yaml` (or inject via Vault).
3. Rolling restart the ml-service pod.

### Emergency fallback

If the GAN produces invalid puzzles in production, set `GAN_ENABLED=false`
in the ml-service environment.  The `POST /api/puzzles/generate-gan` route
on game-service will return a 503 with `{ "error": "GAN generation disabled" }`,
and the mobile app falls back to the engine-generated puzzle queue.

---

## 3. Puzzle Embeddings

### Purpose
Embed puzzle features into 384-dim vectors stored in Qdrant (`puzzles` collection)
for semantic similarity search.

### Embedding model
`all-MiniLM-L6-v2` from sentence-transformers.  Vectors are L2-normalised.

### Indexing new puzzles

Puzzles are indexed automatically when created via the game-service if the
`AUTO_INDEX_PUZZLES=true` env var is set.  To batch-index existing puzzles:

```bash
cd ml/scripts
python index_puzzles.py \
  --db-url postgresql://sudoku:password@localhost:5432/sudoku_ultra \
  --qdrant-url http://localhost:6333 \
  --batch-size 100
```

### Re-indexing from scratch

```bash
python index_puzzles.py \
  --db-url $DATABASE_URL \
  --qdrant-url $QDRANT_URL \
  --reset    # drops and recreates the puzzles collection
```

### Monitoring

- Check collection size: `GET http://qdrant:6333/collections/puzzles`
- If `points_count` is 0, semantic search will return empty results — run
  the indexing script above.

---

## 4. User Preference Embeddings

### Purpose
Aggregate a user's play history into a 384-dim preference vector stored in
Qdrant (`users` collection) for personalised puzzle recommendations.

### When vectors are updated

User vectors are re-indexed automatically after each completed game session
via `POST /ml/api/v1/search/index/user` (called internally by game-service).

### Manual re-index for a specific user

```bash
curl -X POST http://localhost:3003/api/v1/search/index/user \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "<UUID>",
    "sessions": [
      { "difficulty": "hard", "time_elapsed_ms": 120000, "status": "completed", "score": 850 }
    ]
  }'
```

---

## 5. RAG Technique Tutor

### Data source

The `techniques` Qdrant collection holds 20 technique documents seeded by
`ml/scripts/seed_techniques.py`.

### Re-seeding techniques

```bash
# In docker-compose (restarts the one-shot init service):
docker-compose -f infra/docker-compose.yml up qdrant-seed

# Manually:
python ml/scripts/seed_techniques.py \
  --qdrant-url http://localhost:6333 \
  --reset
```

### Adding a new technique

1. Add a new dict to the `TECHNIQUES` list in `ml/scripts/seed_techniques.py`.
   Required fields: `id`, `name`, `origin`, `concept`, `method`, `visual_description`,
   `difficulty_level`, `prerequisite_techniques`, `tags`.
2. Re-run the seed script with `--reset`.
3. No model retraining required — the embedding is computed at seed time.

### LLM model

Default: `llama3` via Ollama (staging) or HuggingFace Inference API (production).

To change the Ollama model:
```bash
# Pull the new model (do this before restarting ml-service)
docker exec sudoku-ultra-ollama ollama pull mistral

# Set OLLAMA_MODEL=mistral in the ml-service environment
kubectl -n sudoku-ultra set env deployment/sudoku-ultra-ml-service OLLAMA_MODEL=mistral
```

### Fallback behaviour

If Qdrant is unreachable → rule-based keyword matcher (returns canned answers).
If Ollama is unreachable → returns the raw retrieved chunks without LLM synthesis.

---

## 6. MLflow

MLflow tracks experiments for the classifier and GAN.

| URL | Environment |
|---|---|
| `http://localhost:5000` | Local docker-compose |
| `http://mlflow.sudoku-ultra-staging.svc:5000` | Staging |
| `http://mlflow.sudoku-ultra.svc:5000` | Production |

### Useful commands

```bash
# List registered models
mlflow models list

# Download a model artifact
mlflow artifacts download -r runs:/<RUN_ID>/model -d ./local_model

# Compare runs in a browser
mlflow ui --backend-store-uri postgresql://$DATABASE_URL
```

---

## 7. Incident Response

### Symptom: Tutor always returns fallback answers

1. `kubectl -n sudoku-ultra logs deployment/sudoku-ultra-ml-service | grep qdrant`
2. Check Qdrant is healthy: `kubectl -n sudoku-ultra exec -it qdrant-0 -- curl localhost:6333/readyz`
3. If `techniques` collection is empty, run the seed job (see §5 above).
4. Check Ollama pod: `kubectl -n sudoku-ultra logs deployment/sudoku-ultra-ollama`

### Symptom: Semantic search returns no results

1. Check `puzzles` and `users` collection sizes in Qdrant dashboard.
2. If empty, run `index_puzzles.py --reset` (see §3 above).

### Symptom: GAN generates puzzles with no unique solution

1. Check ml-service logs for backtracking retries: high retry counts indicate
   the generator checkpoint has regressed.
2. Set `GAN_ENABLED=false` to disable GAN generation (fallback to engine).
3. Retrain the GAN with a fresh dataset and re-deploy after validation.

### Symptom: XAI endpoint returns 500

1. `kubectl -n sudoku-ultra logs deployment/sudoku-ultra-ml-service | grep xai`
2. The SHAP explainer requires the difficulty classifier to be loaded.
   Confirm `MLFLOW_TRACKING_URI` is set and the `difficulty-classifier`
   model is in the `Production` stage.
