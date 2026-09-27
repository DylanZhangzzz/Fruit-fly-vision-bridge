# Frozen offline visual-response benchmark / 统一离线视觉基准

This workflow builds on repository commit `3f60f3e`. It compares **the same RGB movies**, not identically calibrated neurons. It also reads Flyvis L2 predictions at the image positions of published MaleCNS L2 sightlines. This is engineering integration and predictive diagnostics, not new biological validation or full-brain control.

The live bridge now supports both eyes, but this frozen protocol intentionally retains the original 893 right-eye IDs and archived right-eye results. Integrating the binocular implementation does not extend the benchmark's tested field or silently change its population.

Publication includes synthetic results, source-specific attribution and full applicable notices. It excludes raw camera recordings and pretrained weights. See the [rights review](license-review.md) for the unlicensed author-code and separate model-weight boundaries. Archived execution hashes remain unchanged when the HTML is re-rendered to add attribution; `publication.json` records the publication renderer separately.

## Reproduce without a camera

Use a separate Python **3.12** environment; Flyvis currently requires Python <3.13. Run from a checkout:

```powershell
python -m venv .venv-benchmark
.venv-benchmark\Scripts\python -m pip install -e . -r requirements-benchmark.txt
.venv-benchmark\Scripts\python scripts/fetch_benchmark_models.py
.venv-benchmark\Scripts\python -m flyvisionbridge.benchmark --flyvis-root outputs/flyvis-data --output outputs/benchmark
```

On Linux/macOS substitute `.venv-benchmark/bin/python`. The author archive is approximately 3.4 MB; installing PyTorch and the analysis dependencies requires substantially more storage. The fetcher verifies the author's archive SHA-256. At runtime, extracted checkpoint/config bytes must match that archive, and upstream package revisions must match the source manifest. Existing output directories are refused.

Open `outputs/benchmark/index.html` locally, or serve the checkout with `python -m http.server 8770 --bind 127.0.0.1`. Optional `--cases static flash_dark_20ms` makes a logged subset run, not the complete suite.

## What runs

| Method | Actual computation | Units / boundaries |
|---|---|---|
| L2 | Published rounded recurrent-equation parameters, vectorized over observed MaleCNS ray samples; RK4 at ≤0.25 ms, frame held constant over 20 ms | Depolarization-positive effective state in arbitrary units. Not ΔF/F, mV or Hz. Does not choose a favorable fold from the previous physiology benchmark. |
| Flyvis | Official pretrained `flow/0000/000`, unchanged weights, 45,669 nodes / 1,513,231 edges; native BoxEye; upstream integration | Native network state, arbitrary units. Model 000 selected lexicographically before results, not the best network or ensemble. |
| FlyDrones | Official Retina and InputEncoder, unchanged defaults; MiniFly supplies configured group indices | Engineered Poisson input rates; no MiniFly dynamics, MaleCNS dynamics, motor decoder or flight. Its T4-labelled input groups combine motion channels; they are not measured T4 voltages. |

Pins and source/archive hashes are in `flyvisionbridge/benchmark_sources.json` and each result. Windows requires a process-local workaround for datamate 1.0.0 trying to unlink an open HDF5 cache file. The compatibility function closes the file through a context manager; it does not edit upstream source, model equations or weights. The checkpoint is loaded with `weights_only=True`.

## Frozen protocol and comparison limits

`flyvisionbridge/benchmark_protocol.json` is written before any model result. The 13 cases are static gray, dark/light 20 ms and 200 ms flashes, left/right gratings, four moving edges, expansion and contraction. Movies are 416×416, 50 frames/s, 1.6 seconds, with a **synthetic assumed 90° pinhole view**. These dimensions and field of view are benchmark choices, not fly-eye calibration. Two reset runs per case check determinism; no gain fitting, lag alignment or weight optimization occurs.

The same RGB byte hash enters all three methods. Native spatial footprints are retained: L2 center-ray samples, Flyvis 13×13 box averages and FlyDrones resized grids. Consequently population means cover different positions. Do not interpret amplitude differences as errors against a common ground truth.

We report per-method finite outputs, repeat differences, native-unit baselines/peaks, descriptive direction-pair contrast and wall times. L2/Flyvis states are labelled at frame end; FlyDrones rates are labelled at input-frame time. Recorded peak times have 20 ms resolution. Runtime includes native preprocessing, integration where applicable and readout; excludes initialization, disk I/O and the additional spatial interpolation. Repeats are sequential on the same CPU, with four PyTorch threads. Timings do not rank full-brain simulators or biological reflex latency.

Direction diagnostics use `(A-B)/(A+B)` on the mean absolute baseline-subtracted responses during the active interval. They are not trained classifications, and a sign is not a biological preferred direction without a validated model-axis correspondence. L2 direction/loom classification and FlyDrones L2 physiology are explicitly **not covered**. Without independent recordings, no accuracy, RMSE against biology, or universal pass rate is reported.

## Spatial response bridge

1. Retain all 893 published target IDs and their provenance; project available sightlines through explicit rectified intrinsics and the existing assumed forward camera mount.
2. Feed the resulting code-luminance time series to fixed L2 dynamics. Missing directions/out-of-view samples remain NaN. Unknown history invalidates subsequent state; it is not replaced by black or a silent reset.
3. Feed the same RGB frames to native Flyvis BoxEye. Check L2 lattice order against the actual network's `(u,v)` nodes.
4. Interpolate the resulting L2 field at each observed camera pixel using Delaunay barycentric weights. Save source pixel positions, vertices, weights and support masks. Outside the convex hull remains NaN.

**This is an image-space readout, not a biological Flyvis-cell ↔ MaleCNS-ID join.** Spatial receptive fields, specimen identities, physical acceptance angles and camera mounting are still unresolved. In the frozen synthetic view, 252 IDs are visible and 217 lie within the Flyvis interpolation hull. These are ID counts, not distinct-cell physiological validations. No full-brain input is replaced; no arbitrary Hz conversion is added.

## Replay existing D435i recordings

For a local controlled-screen run containing `capture.json` and `rgb.avi`:

```powershell
.venv-benchmark\Scripts\python -m flyvisionbridge.benchmark --flyvis-root outputs/flyvis-data --output outputs/benchmark-with-replay --capture-run PATH_TO_PRIVATE_RUN --replay-start 8 --replay-seconds 4
```

Recorded camera timestamps select frames causally at the benchmark rate; mixed/nonmonotonic clocks and gaps >50 ms are rejected. Rectified intrinsics are mandatory. Frame-size changes require explicit updated intrinsics; the adapter prohibits silent BoxEye resizing. This path is clearly **uncorrected camera-code response prediction**, not the calibrated photometry/temporal acceptance workflow. It does not bypass that workflow's explicit local calibration requirement or claim a radiance conversion. Prior adaptation before the replay segment is unknown; the models start from protocol gray/rest states. Depth and IMU are not scored in this benchmark.

Private replay output stays under ignored `outputs/`. No camera thumbnails are generated. Do not publish that output automatically. The synthetic-only export excludes camera case metadata, traces and arrays:

```powershell
.venv-benchmark\Scripts\python scripts/export_benchmark_report.py outputs/benchmark-with-replay reports/benchmark
```

## Files and checks

- `report.json`: cases, native model definitions, hashes, package versions, scope, runtimes, support.
- `metrics.csv`, `direction_diagnostics.json`: descriptive comparisons, no fitted readout.
- `<case>.npz`: time axes, camera samples, per-ID L2 states, native and interpolated Flyvis L2, FlyDrones group rates. IDs remain in original mapping order, with NaN for unsupported results.
- `spatial_columns.csv`, `spatial_weights.npz`: every ID, supported/unknown status and reproducible readout weights.
- `index.html`: self-contained interactive mean-response plots; CSV and array links require adjacent files.

`python scripts/run_checks.py` runs offline source checks and implementation tests. Added tests use analytic no-feedback solutions, causality, known stimulus geometry, affine-field interpolation and unknown-support preservation. They are not biological validation. The manual `Offline visual benchmark` GitHub workflow additionally installs the pinned upstreams and runs the complete synthetic comparison.

下一步需要把方向与空间接受范围标定到共同视觉坐标，并找到对应新刺激的独立生理记录；本次结果不能证明模型已经学会真实场景感知。
