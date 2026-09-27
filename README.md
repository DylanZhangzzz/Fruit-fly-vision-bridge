# Fruit-fly-vision-bridge

[中文说明](README.zh-CN.md) · [Findings](docs/findings.md) · [Installation](docs/installation.md) · [Contributing](CONTRIBUTING.md)

An experimental bridge from camera images to published fruit-fly visual columns, with separate checks for geometry, camera acquisition, and neural-response models.

This project connects **published anatomical directions to MaleCNS L2 IDs**, samples observed RGB along those directions, and keeps depth and IMU as auxiliary geometric measurements. It also benchmarks an L2 temporal model against public live-fly voltage-indicator recordings. It is not an official camera API for a fly brain, and does not claim a biologically validated whole-brain visual system.

## Current evidence

| Layer | Result | What it establishes |
|---|---|---|
| Published anatomy | Right: 847/893 IDs, 846 columns; left: 847/886 IDs, 847 columns; 85 IDs unresolved across both eyes | Exact eye-specific joins to author-published cross-specimen anatomical estimates |
| Controlled screen → D435i | 21 L2 IDs / 20 columns passed the recorded temporal engineering criteria, at approximately 59.53 RGB frames/s | Transmission under the tested geometry and fixed black/white reference patches |
| Public L2 physiology | 103 selected ROI records from 13 flies, whole-fly leave-one-out: mean r=0.750, R²=0.447, RMSE=0.00663 ΔF/F | Limited same-study, same-flash-type cross-fly prediction |
| Important failures | 5 selected records had R²≤0; parameters reached bounds in 10/14 total folds | No universal cell pass, unique parameter identification, or new-stimulus validation |

The recurrent model improves over a separately fitted feedback-free model for 11/13 flies, but has **no demonstrated advantage over the training-fly mean waveform template** for the same stimulus. ROI records are not MaleCNS neuron IDs. Detailed provenance, negative results, units and exclusions are in [the findings](docs/findings.md).

## Try it without hardware

Requires Python 3.11+; Python 3.12 on Windows was used for the clean installation check. From a clone:

```sh
python -m venv .venv
# Activate: Windows PowerShell: .venv\Scripts\Activate.ps1
# Activate: Linux/macOS: source .venv/bin/activate
python -m pip install -e .
python -m flyvisionbridge.cli --demo --output outputs/demo
python scripts/run_checks.py --core-only
```

The synthetic demo writes `rgb.png`, assumed demonstration intrinsics, and `channels.json`. It uses the included published mapping, records all 893 IDs, leaves unobserved/missing directions null, and **does not open a camera or generate neural firing rates**. Choose a new output directory for each run.

## Connect a webcam to the brain

The new live entry runs the complete **RGB → mapped L2 → engineering rates → persistent BrainCPU → downstream activity** chain:

```sh
python -m pip install -e ".[analysis]"
python -m flyvisionbridge.live --model-dir PATH_TO_FRUIT_FLY_SIMULATION --device-name "Logitech BRIO" --assume-hfov 90
```

Open `http://127.0.0.1:8771/` and start a bounded capture. Install Node.js, the external model, and FFmpeg first as described in [the live webcam guide](docs/webcam-live.md). OpenCV-indexed cameras use `--camera 0` instead of `--device-name`. Intrinsics must be provided or a provisional FOV explicitly assumed; 90° is an example assumption, not a BRIO calibration.

The live entry now defaults to **both eyes**; select `--eyes left`, `--eyes right` or `--eyes both`. The left map adds 847/886 resolved L2 IDs using separate published left-eye tables. A saved BRIO frame drove 229 left + 217 right inputs in full-model replay; this new binocular mode still needs a fresh hardware acquisition run. See [binocular setup and evidence](docs/binocular.md).

The historical right-eye physical BRIO/Windows run drove 217 visible L2 channels into the 166,700-neuron graph, retained state across frames, and passed zero-input/disconnected/half-gain controls. See [the aggregate hardware report](reports/webcam/README.md). Default operation advances 20 ms of model time at five updates/s (0.1× wall time). This is engineering integration, not biological response validation.

## Reproduce the research workflows

```sh
python -m pip install -e ".[analysis,camera]"
python scripts/run_checks.py
python camera_lab/biomapping/import_atlas.py
python camera_lab/biomapping/import_author_map.py
# Public physiology data are optional and downloaded separately:
python scripts/fetch_data.py
python camera_lab/biomapping/validate_l2_cells.py
```

Dryad sometimes requires a normal browser download. The fetcher prints the official page and accepts `--from-directory PATH`; it verifies the same SHA-256 either way. See [installation and data](docs/installation.md). Hardware-free implementation checks do not download the 117 MB physiology recording or acquire camera frames.

For **D435i**, use the existing bounded RGB-D-IMU recorder and controlled screen experiment. For an **ordinary RGB webcam**, use the [live brain bridge](docs/webcam-live.md); the BRIO/Windows FFmpeg path has been physically exercised. OpenCV-indexed hardware still needs separate qualification. For a **saved image or single-frame sample**, use the camera-independent RGB CLI with explicit rectified intrinsics. See [camera instructions](docs/cameras.md). Other depth cameras must supply their own registration and timestamp adapter.

## Project layout

```text
flyvisionbridge/           Frame contract, single-frame CLI, live camera/brain worker and dashboard
camera_lab/               D435i acquisition, calibration and historical BrainCPU tools
  biomapping/             Anatomical joins, screen experiments, physiology benchmarks
    source/               Small licensed mapping inputs and public-data manifest
    data/                 Derived mappings and provenance
scripts/                  Source verification, data acquisition, unified checks
tests/                    Camera-independent bridge tests
docs/                     Installation, mapping, validation, findings and roadmap
reports/                  Shareable archived results, with limitations
.github/                  CI, issue forms and pull-request template
```

Open [reports/index.html](reports/index.html) after cloning, or run `python -m http.server 8000 --bind 127.0.0.1` and visit `http://127.0.0.1:8000/reports/`. GitHub displays HTML source rather than running the interactive report. Raw camera videos, room images, device serials, virtual environments and full connectome weights are excluded.

## Scope and next work

- Missing directions and out-of-view rays stay unknown; a narrow camera is not stretched across the whole compound eye.
- Weighted RGB code is not calibrated radiance. Depth is not an extra fly range sensor; IMU is not injected into invented fly neurons.
- The historical `120*(1-L)` Hz input is an engineering stimulus. The physiology output is ASAP2f ΔF/F, not mV or Hz; neither is silently substituted for the other.
- Camera mounting, IMU bias/timing, photoreceptor acceptance angles and natural-scene responses remain unvalidated.
- The next physiology milestone is **frozen-parameter prediction of genuinely held-out stimulus conditions**, with appropriate independent recordings and baselines. It has not been completed here.

Read [validation](docs/validation.md), [mapping](docs/mapping.md), and [roadmap](docs/roadmap.md) before interpreting a passing test as biological evidence.

Contributions and questions are welcome in [Issues](https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/issues). Follow [CONTRIBUTING.md](CONTRIBUTING.md), especially when adding a camera adapter, public dataset or scientific claim.

## Sources and licensing

Project code is GPL-3.0-only. Third-party files and derived data retain their stated terms, including GPL-3.0 and CC BY-SA 4.0 for mapping resources; the public Dryad physiology dataset is CC0. Do not apply the code license to every data file. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [sources](docs/sources.md) and [CITATION.cff](CITATION.cff). This is an independent integration and validation project; upstream authors did not validate this bridge.
