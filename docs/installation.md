# Installation and reproducibility

Run commands from the repository root. A clone is the supported research workflow; the small `fly-vision` RGB CLI is also packaged. Windows/Python 3.12 is the locally checked environment; GitHub Actions is configured for Windows and Ubuntu/Python 3.12. A configured job is not itself evidence that a platform passed.

## Environment

```sh
git clone https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge.git
cd Fruit-fly-vision-bridge
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on PowerShell or `source .venv/bin/activate` on POSIX shells. If activation is unavailable, use `.venv\Scripts\python.exe` / `.venv/bin/python` directly. Do not change machine security policy just to activate a virtual environment.

```sh
python -m pip install -e .                     # Synthetic / saved RGB bridge
python -m pip install -e ".[analysis,camera]"   # All research checks and D435i scripts
python -m pip check
python scripts/run_checks.py
```

The RealSense SDK is imported by the device tools and one SDK-vs-geometry test. No test opens a physical camera. A platform without a compatible `pyrealsense2` wheel can still run `pip install -e .` and `scripts/run_checks.py --core-only`; install the SDK using its [official instructions](https://github.com/realsenseai/librealsense) for hardware work. This repository does not install firmware or overwrite device calibration.

`requirements-reproduction.txt` records the key versions of the original analysis. `reports/reproduction/environment.json` records the separately tested clean environment. They serve different purposes: the former identifies the historical calculation, the latter shows the release checkout was exercised with fresh dependencies.

## Mapping data

Small authoritative mapping inputs, their licenses, derived tables and byte hashes are included. No access token is needed.

```sh
python scripts/verify_sources.py
python camera_lab/biomapping/import_atlas.py
python camera_lab/biomapping/import_author_map.py
python -m camera_lab.biomapping.import_left_eye
python camera_lab/biomapping/test_author_map.py
```

`import_atlas.py` reconstructs a 778-ray reference product and an unresolved MaleCNS identity audit. `import_author_map.py` then joins the separate author-published MaleCNS angle product. The unresolved intermediate file is deliberately retained; it does not override the final mapped table.

## Physiology data

The 117,007,438-byte `L2_ASAP2f.mat` is not in Git. Required files, official URLs and fixed SHA-256 values are in `data/downloads.json`.

```sh
python scripts/fetch_data.py
```

If Dryad returns an access page or rejects programmatic downloading, use the [official dataset page](https://datadryad.org/dataset/doi:10.5061/dryad.ngf1vhj4c) in a browser. Download the exact files `L2_ASAP2f.mat`, `L1L2_Metadata.xlsx` and `README.md` into one folder, then:

```sh
python scripts/fetch_data.py --from-directory PATH_TO_DOWNLOAD_FOLDER
python scripts/fetch_data.py --verify-only
python camera_lab/biomapping/validate_l2_cells.py
```

The two small author mean-response MAT files are fetched from a pinned GitHub commit if absent. A mismatch stops the workflow; it never silently accepts a newly updated file. Data files are parsed, not executed. Results are written to `camera_lab/biomapping/physiology_validation/`; archived reference results in `reports/physiology/` remain separate. A run normally takes minutes, depending on the machine and numerical libraries. Numerical comparison should use tolerances, not byte equality of fitted floating-point parameters.

## Reports and optional whole-brain replay

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Visit `http://127.0.0.1:8000/reports/`. The browser report uses local files; no CDN is required. The archived camera summary can be inspected, but reproducing its measured result requires a new physical recording because private raw videos are not published.

The external BrainCPU engine is optional. It is not needed for the RGB bridge, mapping checks or physiology benchmark. For the live webcam bridge or historical whole-brain controls, install Git LFS and Node.js 22.12+ separately, then obtain the original project:

```sh
git clone https://huggingface.co/spaces/Xenova/fruit-fly-simulation fruit-fly-simulation
git -C fruit-fly-simulation checkout 776d115ee5aa934578a87fd6d260d138084f59c1
git -C fruit-fly-simulation lfs pull
python camera_lab/biomapping/run_malecns.py PATH_TO_MULTIMODAL_CAPTURE
```

This downloads substantial external assets under their own licenses. The loader verifies connectome chunk hashes. `run_reference.py --malecns` also needs this metadata to emit BrainCPU-indexed inputs. The single-frame RGB CLI needs none of it. The [live webcam entry](webcam-live.md) uses this model through `--model-dir`; named Windows cameras additionally require FFmpeg on PATH. No browser permission or microphone is needed because capture runs locally in Python/FFmpeg. The old pixel-grid audit requires your recording path through `FLYVISION_LEGACY_CAPTURE`; it tests an earlier artificial grid and is not the preferred author-angle mapping workflow.
