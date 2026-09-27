# Live webcam → whole-brain bridge

This path completes the camera-to-model chain. It captures fresh RGB frames,
samples author-mapped L2 directions, converts observed brightness into an
explicit engineering drive, advances the **same persistent BrainCPU instance**,
and shows both input and downstream spikes in a local dashboard.

It has been physically exercised with a Logitech BRIO on Windows, using FFmpeg
DirectShow capture, at 640×480 and 30 requested camera frames/s. OpenCV camera
indices are also supported by the adapter, but that capture backend has not yet
been physically qualified in this project. A no-input baseline, a disconnected
network and a half-input-gain control are included.

## Start

Install the Python extras, Node.js 22.12+, and the separate upstream model as
described in [installation](installation.md). `--model-dir` identifies the
directory containing `src/brain.js` and `public/data/manifest.json`.

For a Windows camera with an unambiguous friendly name, install FFmpeg from its
official distribution, make `ffmpeg` available on PATH, and run:

```powershell
python -m flyvisionbridge.live --model-dir PATH_TO_FRUIT_FLY_SIMULATION --device-name "Logitech BRIO" --assume-hfov 90
```

Open **http://127.0.0.1:8771/** and press **开始采集**. The default acquisition
lasts 60 seconds and releases the camera on completion. The model stays loaded
while the server is idle. Another run explicitly resets the model, then holds
state across its successive input frames. Use the stop button to finish early.
Ctrl+C stops the server and model too; `POST /api/shutdown` performs the same
cleanup for a hidden local server. Camera frames are never sent to a remote host.

`--assume-hfov 90` is an **explicit provisional projection**, not a measured BRIO
field of view or calibrated eye orientation. It is useful for getting the chain
running, but cannot certify angular accuracy. Replace it with calibrated
intrinsics when available:

```sh
python -m flyvisionbridge.live --model-dir PATH_TO_MODEL --camera 0 --intrinsics camera.json
```

`--backend dshow` / `msmf` selects an OpenCV backend on Windows; `--backend v4l2`
is available on Linux. `--device-name` instead uses FFmpeg/DirectShow and is
Windows-specific. Device names must refer to a video device; no audio is opened.
An installed FFmpeg executable can be selected with `--ffmpeg PATH`.

The live path rectifies **standard OpenCV Brown/rational distortion** when
nonzero coefficients are supplied. It masks invalid rectification borders rather
than interpreting black padding as strong neural input. Fisheye/inverse models
need a separate adapter. `--head-from-camera rotation.json` supplies an explicit
proper rotation; otherwise the existing forward-facing bench assumption is used.

## Timing and what the display means

Defaults are five model updates per wall-clock second and **20 ms of model time
per update**. Consequently the nominal model speed is 0.1× wall-clock time; this
is a continuously updated live bridge, not a claim of 1× biological real time.
Change `--updates-per-second` and `--model-ms` together if you want a different
operating point. The UI reports the achieved speed rather than assuming it.

A capture thread continuously drains the camera. If model processing is slower,
the next update takes the latest frame and reports the skipped camera frames.
It does not build a growing queue or pretend the skipped visual history was
simulated. Input is held during each model interval. Timestamps are host receipt
times, not measured exposure times or photon-to-spike latency.

The engineering conversion is `rate_hz = gain_hz × (1 − RGB code luminance)`,
with `--gain-hz` in 0..120 and default 120. It bypasses a biologically validated
photoreceptor model. Unknown, outside-field or invalid-border samples produce
no input entry; the worker clears old rates every update to avoid stale drive.
Only IDs verified as **right-eye L2** in the model metadata are accepted.

The full graph is loaded once. Compressed connection chunks are checked against
the upstream manifest. Model/metadata/manifest hashes are saved. The upstream
engine is not changed. Dashboard spikes are simulated spikes, not live-fly
recordings; this feature does not calibrate physical radiance or biological
response. A webcam supplies no depth or IMU, and those fields remain unavailable.

## Controls and local evidence

At the first frame, the same captured input is replayed from reset, with fixed
seed, in four conditions: zero input, camera input, connections disabled, and
half input gain. A successful result shows camera-driven input/downstream activity,
zero activity at rest, and no downstream activity when connections are disabled.
A black/white or hand-occlusion change can then be observed in the continuous
input. Changes in a stochastic network alone do not prove a causal visual effect;
the reset-matched controls are the stronger software-path check.

The **重跑输入 / 断连对照** button tests the current frame and explicitly resets
the model afterward; this reset is logged. Ordinary frame updates do not reset it.

Each bounded run writes to ignored `outputs/webcam-live/TIMESTAMP/`:

- `first_rgb.jpg`: private first frame; do not publish automatically.
- `first_input.json`: sampled body IDs and engineering rates.
- `initial_controls.json`: reset-matched model comparisons.
- `frames.jsonl`: frame sequence, input rates, model ticks, timings and responses.
- `summary.json`: continuity, observed input variation, aggregate activity and scope.

Only a sanitized aggregate report is committed. Neither camera images nor
per-frame private observations belong in Git. The source is usable with other
RGB webcams; new camera/backend combinations still need their own checks.

See [the BRIO hardware evidence](../reports/webcam/README.md) for the measured
run and reset-matched contrast replay. To generate an aggregate report from
your own completed capture:

```sh
python scripts/export_webcam_report.py outputs/webcam-live/YOUR_RUN --output outputs/webcam-report.json --model-dir PATH_TO_MODEL
```

The optional model argument replays the recorded lowest/highest mean-brightness
inputs with the same initial state and seed. It verifies matching model hashes;
it does not turn this post-hoc contrast check into a biological validation.
