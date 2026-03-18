# Performance Profiling Guide

This document covers performance profiling for the Sudoku Ultra mobile app,
focusing on the Edge AI inference pipeline (classifier, clustering, scanner)
and the offline queue sync path.

---

## Tools

| Tool | Purpose | Platform |
|------|---------|---------|
| Flipper → Performance | Timeline of custom `perf.ts` marks | iOS + Android |
| Flipper → Network | Inspect API calls (ML classify, sync) | iOS + Android |
| Xcode Instruments | CPU + memory profiling, GPU timeline | iOS |
| Android Studio Profiler | CPU / memory / network / energy | Android |
| `edgeAI.benchmark.ts` | Simulated 3-model × 3-device CI benchmark | Jest / Node |
| `check_sla.py` | ML model accuracy SLAs in CI | Python / GitHub Actions |

---

## 1. Quick CI Benchmark

Run the simulated device-profile benchmark without a physical device:

```bash
cd apps/mobile
npx ts-node src/benchmarks/edgeAI.benchmark.ts
```

Expected output (all `PASS`):

```
Model         Device       Median ms  Limit ms  Status
classifier    high-end            18        50  PASS
clustering    high-end            12        50  PASS
scanner       high-end            25        50  PASS
classifier    mid-range           55       100  PASS
...
```

Fail criteria: any model × device combination exceeds `hardLimitMs`.

---

## 2. Flipper Integration

`perf.ts` connects to Flipper automatically when `react-native-flipper` is
installed and the Flipper desktop app is open.

### Setup

```bash
# Install (dev only — already in package.json devDependencies)
npm install --save-dev react-native-flipper

# iOS
cd ios && pod install
```

### Instrumenting new code

```typescript
import { perf } from '../utils/perf';

// Option A — manual mark/measure
const mark = perf.mark('myFeature:step1');
await doWork();
const ms = perf.measure(mark);
console.log(`step1 took ${ms}ms`);

// Option B — timed async helper
const { result, durationMs } = await perf.time('myFeature:total', () => doWork());
```

### Reading the timeline

1. Open Flipper → **Performance** → **Timeline**
2. Filter by `sudoku-ultra-perf` plugin
3. Look for marks prefixed with `classifier:`, `clustering:`, `scanner:`, `offlineQueue:`

---

## 3. On-Device Profiling

### Android (Android Studio Profiler)

1. Launch the app in debug mode: `npx expo run:android --variant debug`
2. Open Android Studio → **View** → **Tool Windows** → **Profiler**
3. Attach to `com.sudoku.ultra` process
4. Select **CPU** → **Record** → reproduce inference → **Stop**
5. In the flame chart, filter for `onnxruntime` and `classifyDifficulty`

**Key metrics to capture:**

| Metric | Target |
|--------|--------|
| `InferenceSession.run()` duration | ≤50ms (high-end), ≤200ms (low-end) |
| JS → Native bridge latency | ≤5ms |
| Memory during inference | ≤50 MB delta |

### iOS (Xcode Instruments)

1. Build release-like dev build: `npx expo run:ios --configuration Release`
2. Product → **Profile** (⌘I) → **Time Profiler**
3. Start recording, run a game session, stop
4. Filter call tree to `OrtInferenceSession` and `classifyDifficulty`

---

## 4. Offline Queue Profiling

The offline queue (`offlineQueue.service.ts`) uses AsyncStorage writes on
every `enqueue()` and `sync()` call.

### Measuring queue write latency

```typescript
import { perf } from '../utils/perf';
import { offlineQueue } from '../services/offlineQueue.service';

const mark = perf.mark('offlineQueue:enqueue');
await offlineQueue.enqueue(gameResult);
const ms = perf.measure(mark, 'offlineQueue:enqueue');
// Expect <10ms on all devices
```

### Stress testing the sync path

```bash
# In the RN dev console (Expo Go or dev client):
# 1. Enable Airplane Mode
# 2. Complete 50 games (or call offlineQueue.enqueue() 50 times)
# 3. Re-enable network
# 4. Monitor Flipper → Network for the flush requests
```

Expected: 50 POST requests in batches of 20, all complete within 5 seconds on
a 4G connection.

---

## 5. ONNX Model Size Targets

| Model | File | Target size |
|-------|------|------------|
| difficulty-classifier | `classifier.onnx` | ≤500 KB |
| skill-clustering | `clustering.onnx` | ≤100 KB |
| digit-scanner | `scanner.onnx` | ≤2 MB |
| digit-scanner (quantised) | `scanner.tflite` | ≤500 KB |

Check current sizes:

```bash
# Via API:
curl http://localhost:8003/api/v1/edge/status | jq '.models'

# Locally:
ls -lh services/ml-service/ml/models/*.onnx services/ml-service/ml/models/*.tflite 2>/dev/null
```

---

## 6. OTA Update Bundle Size

The OTA update workflow (`.github/workflows/ota-update.yml`) enforces a 25 MB
Android bundle limit. To check locally:

```bash
cd apps/mobile
npx expo export --platform android --output-dir /tmp/bundle-check
du -sh /tmp/bundle-check
```

If the bundle exceeds the limit:
1. Audit imports with `npx expo-bundle-analyzer`
2. Move large assets to CDN (S3 / CloudFront)
3. Ensure ONNX models are fetched from `/api/v1/edge/models/*` at runtime,
   not bundled with the JS bundle

---

## 7. Performance Budget Summary

| Scenario | P50 target | P95 target | Hard limit |
|----------|-----------|-----------|-----------|
| Classifier inference (high-end) | 18ms | 30ms | 50ms |
| Classifier inference (mid-range) | 55ms | 80ms | 100ms |
| Classifier inference (low-end) | 130ms | 180ms | 200ms |
| API fallback (Tier 2) | 150ms | 400ms | 3000ms |
| Rule-based fallback (Tier 3) | <1ms | <1ms | 5ms |
| Offline queue enqueue | 5ms | 10ms | 20ms |
| Offline queue sync (per entry) | 200ms | 800ms | 3000ms |
| OTA bundle size (Android) | — | — | 25 MB |

---

## 8. Regression Detection

Performance regressions are caught at three levels:

1. **CI benchmark** — `edgeAI.benchmark.ts` fails build if any simulated
   device profile exceeds `hardLimitMs`
2. **ML SLA CI** — `check_sla.py` verifies model accuracy metrics; a slower
   model is often a sign of increased complexity
3. **Nightly drift check** — `model-drift` Airflow job monitors inference PSI;
   spikes can indicate data or model issues that increase latency indirectly

To add a new performance regression test:

```typescript
// apps/mobile/src/tests/myFeature.benchmark.test.ts
import { perf } from '../utils/perf';
import { myFeature } from '../services/myFeature';

it('myFeature completes in <100ms', async () => {
    const { durationMs } = await perf.time('myFeature', () => myFeature());
    expect(durationMs).toBeLessThan(100);
});
```
