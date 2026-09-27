# Validation layers and reproduction commands

Keep implementation correctness, engineering performance and biological evidence separate.

## 1. No-hardware checks

`python scripts/run_checks.py` verifies 10 source-file hashes and runs the bridge, projection, calibration, exact-join, optical-code, frozen-LUT and temporal-model tests. The package release currently has 57 implementation tests. A synthetic chessboard is generated before calibration checks. The tests use known geometric or analytic answers, mutation controls, train/test separation and invalid-input cases; none measures a living fly.

`--core-only` runs the 9 camera-independent bridge tests and source hashes using only NumPy/Pillow. Full checks require the analysis and camera extras, including the RealSense SDK for an offline depth comparison.

## 2. Per-position mapping

```sh
python camera_lab/biomapping/import_atlas.py
python camera_lab/biomapping/import_author_map.py
python camera_lab/biomapping/test_author_map.py
```

Checks cover row-order independence, axis/column corruption, duplicate keys, independent CSV/XLSX exports, every author ray as a spherical point stimulus, preserved shared columns, and projection round trips. They verify implementation against the published map, not independent physiological receptive fields. The historical 893-site artificial camera-grid audit is a different experiment; see `docs/history/` and `FLYVISION_LEGACY_CAPTURE`.

## 3. Camera-on-screen engineering experiment

Run the continuous display workflow in [cameras](cameras.md). The sequence calibrates a monotone same-location gray LUT using training levels, validates held-out levels/repeats, freezes the LUT, then records a separate temporal stimulus. Independent black/white patches correct affine brightness drift before lookup. The correction uses no temporal target gray values.

Original engineering thresholds remain fixed: static error ≤5 codes; sine R²≥0.95 and amplitude error ≤10%; flash-width error ≤60 ms; signed motion-order correlation ≥0.9 and residual ≤100 ms; marker displacement p95≤3 camera pixels. Invalid/flat/extrapolated LUT intervals remain unknown. See the full protocol in the screen directory for acquisition and IMU checks.

Reanalyse your own run with:

```sh
python camera_lab/biomapping/analyze_photometric.py PATH_TO_CALIBRATION_RUN
python camera_lab/biomapping/analyze_calibrated.py PATH_TO_TEMPORAL_RUN
```

The archived passing run does not certify natural scenes, linear physical luminance, biological temporal dynamics, depth precision, or exact RGB/IMU synchrony. Sine phase is free; no absolute latency is inferred. A 60 Hz camera cannot recover millisecond physiology simply by numerical integration at a smaller timestep.

## 4. Public L2 physiology

```sh
python scripts/fetch_data.py --verify-only
python camera_lab/biomapping/test_l2_cells.py
python camera_lab/biomapping/validate_l2_cells.py
```

The protocol `camera_lab/biomapping/l2_physiology_protocol.json` was frozen before the original benchmark outcomes. The released 103-record mean exactly matches the author's fitted high-luminance curve, so the frozen-author-parameter result is a reproduction. The new primary evaluation refits the equation family on all **other flies**, with equal fly weight and train-only scale, baseline, latency and dynamic parameters. No test-ROI gain/lag alignment is allowed.

Compare held-out observed ΔF/F against the recurrent model, separately fitted feedback-free dynamics, training-mean waveform template and constant baseline. Report RMSE, correlation and R² separately, with per-record failures preserved. Average ROI scores within each fly, then weight flies equally. Bootstrap intervals describe this set of flies; folds share training data, so they are not independent external trials.

The source's bin-edge arithmetic is reproduced exactly. Nominal 20 ms flashes are integrated then averaged in trailing 1/120 s windows. The source time labels correspond to bin ends. The original author's three-sample delayed Euler pulse is retained only in the historical reproduction field. Model outputs are effective fluorescence proxies, not calibrated membrane potentials.

## What would strengthen the evidence?

Use a **new stimulus condition or independent dataset**, freeze parameters and preprocessing beforehand, and compare to baselines able to make predictions for that condition. Do not use the new data to choose latency, gain, trial exclusions, parameter bounds or the winning model and then call them held-out. This next step is specified in [roadmap](roadmap.md), not reported as done.
