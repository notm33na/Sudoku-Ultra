# ML Model Assets

Binary model files for on-device (Tier 1) inference via `onnxruntime-react-native`.
All files are gitignored. They must be present before building a release or running
the Tier 1 inference path locally.

## Required files

| File | Source path in CI artifact | Used by |
|---|---|---|
| `classifier.onnx` | `services/ml-service/ml/models/classifier.onnx` | `edgeAI.ts` Tier 1 — difficulty classification |
| `scanner.onnx` | `services/ml-service/ml/models/scanner.onnx` | `ScanPuzzleScreen` — digit recognition |
| `scanner.tflite` | `services/ml-service/ml/models/scanner.tflite` | `ScanPuzzleScreen` — digit recognition (iOS fallback, optional) |

The app degrades gracefully when these files are absent:
- Missing `classifier.onnx` → falls through to **Tier 2** (REST API) then **Tier 3** (rule-based).
- Missing `scanner.onnx` / `scanner.tflite` → `ScanPuzzleScreen` uses REST API scan endpoint.

## Download from CI artifact (recommended)

The GitHub Actions workflow `ML Model Training` uploads all trained models as artifact
`ml-models-{git-sha}` after every successful run.

```bash
# 1. Find the latest successful run ID
gh run list --workflow=ml-training.yml --status=success --limit=1

# 2. Download the artifact (replace RUN_ID with the value from step 1)
gh run download RUN_ID --name ml-models-<sha> --dir /tmp/ml-models

# 3. Copy ONNX files into the mobile assets directory
cp /tmp/ml-models/services/ml-service/ml/models/classifier.onnx \
   apps/mobile/assets/models/classifier.onnx

cp /tmp/ml-models/services/ml-service/ml/models/scanner.onnx \
   apps/mobile/assets/models/scanner.onnx

# Optional — TFLite for iOS Tier 1 scanner
cp /tmp/ml-models/services/ml-service/ml/models/scanner.tflite \
   apps/mobile/assets/models/scanner.tflite 2>/dev/null || true
```

One-liner (after `gh auth login`):

```bash
RUN_ID=$(gh run list --workflow=ml-training.yml --status=success --limit=1 --json databaseId -q '.[0].databaseId')
SHA=$(gh run view "$RUN_ID" --json headSha -q '.headSha[:8]')
gh run download "$RUN_ID" --name "ml-models-${SHA}" --dir /tmp/ml-models
mkdir -p apps/mobile/assets/models
cp /tmp/ml-models/services/ml-service/ml/models/classifier.onnx apps/mobile/assets/models/
cp /tmp/ml-models/services/ml-service/ml/models/scanner.onnx     apps/mobile/assets/models/
cp /tmp/ml-models/services/ml-service/ml/models/scanner.tflite   apps/mobile/assets/models/ 2>/dev/null || true
```

## Build locally from source

Run the full training + export pipeline inside `services/ml-service`:

```bash
cd services/ml-service

# Install deps (skl2onnx required for classifier export)
pip install -r requirements.txt skl2onnx

# Train models
python -m app.ml.train_classifier   # → ml/models/difficulty_classifier.pkl
python -m app.ml.train_scanner      # → ml/models/scanner.pt + scanner.onnx

# Export ONNX
python -m app.ml.export_onnx        # → ml/models/classifier.onnx, scanner.onnx
                                    #   scanner.tflite (requires pip install onnx2tf)

# Copy to mobile assets
cp ml/models/classifier.onnx ../../apps/mobile/assets/models/
cp ml/models/scanner.onnx    ../../apps/mobile/assets/models/
cp ml/models/scanner.tflite  ../../apps/mobile/assets/models/ 2>/dev/null || true
```

## .gitignore

These binary files are excluded in `apps/mobile/.gitignore`:

```
assets/models/*.onnx
assets/models/*.tflite
assets/models/*.pt
```
