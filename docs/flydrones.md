# Use published L2 positions in FlyDrones

This optional adapter replaces FlyDrones' index-order visual mapping with **MaleCNS body ID → published column → published viewing direction → camera pixel**. Both eyes use their own published tables. FlyDrones' LIF simulator remains unchanged.

Supported upstream revision: [`SpikeCalls/FlyDrones@3e269346`](https://github.com/SpikeCalls/FlyDrones/tree/3e269346b3882c291d2a977bc2c2c6a9c9213c21). This is an integration in Fruit-fly-vision-bridge, not a contribution merged upstream or an upstream-endorsed feature.

## Install and reproduce the comparison

From this repository's activated Python 3.11+ environment:

```sh
python -m pip install -e ".[flydrones]"
python -m unittest discover -s tests -p test_flydrones_bridge.py -v
python -m flyvisionbridge.flydrones_comparison --output outputs/flydrones-comparison
```

This uses no hardware, whole-brain download or drone connection. The fixture has **1,779 real L2 identities and empty synthetic wiring**; it tests spatial addressing. Separate integration tests run the actual upstream `Brain.tick` and `Pilot.tick` with small empty synthetic graphs. CI runs those tests on Windows and Linux.

See the [measured results and limitations](../reports/flydrones/README.md) and [versioned comparison protocol](../flyvisionbridge/flydrones_protocol.json). This comparison is separate from the earlier Flyvis/FlyDrones/L2 [response benchmark](benchmark.md).

## What changes in FlyDrones

The upstream defaults drive R1–R6, T4/T5, looming pathways and yaw inputs. Our current published correspondence covers **L2 only**. `l2_config` copies a configuration and **replaces its entire inputs section** with `L2_L` / `L2_R`; this is an explicit alternative input mode. It retains the original dynamics, outputs and bias, which the experimenter must review.

The bridge takes one calibrated camera image and projects each eye's directions into it. It does not assign each eye half of the image, mirror the right eye, fabricate a second camera, or expand the camera's field of view. A subgraph is supported if it preserves real `body_ids`, types and sides. MiniFly lacks the biological ID correspondence and is rejected.

Rate rules are explicit engineering choices:

- `darkness`: `gain_hz * (1 - camera_RGB_code_luminance)`; default 120 Hz, consistent with our existing live bridge.
- `brightness`: `gain_hz * camera_RGB_code_luminance`; used in the spatial comparison to match the upstream brightness input's polarity and gain.

These are engineered Poisson input rates, not measured L2 firing. Depth and IMU remain optional geometric annotations; this L2-only adapter does not inject yaw, hearing, looming or motion-channel physiology.

## Pass a camera frame directly to Brain.tick

Load a **native FlyDrones MaleCNS `.npz`** with real `body_ids` using our [full-network build guide](flydrones-full-network.md), which documents a necessary fallback from missing rootSide to official somaSide annotations. A Xenova `brain.js` model directory is a different format and cannot be passed here. The [full-network qualification](../reports/flydrones-full-network/README.md) now covers 166,700 neurons and 10,520,377 connections under the stated minimum-three-synapse filter; routine CI still uses synthetic wiring fixtures.

```python
import json
import numpy as np
from PIL import Image
from flydrones.config import default_config
from flydrones.brain import Brain
from flydrones.brain.connectome import Connectome
from flyvisionbridge.bridge import Frame
from flyvisionbridge.flydrones_bridge import L2Encoder, l2_config

cfg = l2_config(default_config(), eyes="both", polarity="darkness", gain_hz=120)
con = Connectome.load("malecns.npz")
brain = Brain(con, cfg)  # resolves groups BEFORE constructing the adapter
encoder = L2Encoder(con, cfg)
k = json.load(open("intrinsics.json", encoding="utf8"))
rgb = np.array(Image.open("rectified_rgb.png").convert("RGB"))
frame = Frame(rgb, k, timestamp_s=0.0, clock_domain="SAVED_IMAGE")
drive = encoder.encode_frame(frame)
simulated_rates = brain.tick(drive.rates, ms=50)
print({name: int(mask.sum()) for name, mask in drive.valid.items()})
```

For a stream, keep `brain` and `encoder` alive and repeat the final three lines with each new `Frame`. Webcam and D435 readers share the [same Frame contract](cameras.md). RGB must be `uint8`, H×W×3, with rectified, resolution-matched intrinsics. Pass a measured `head_from_camera` rotation to `L2Encoder`; its default is an explicitly **assumed bench orientation**, not biological mounting calibration. `encode_frame(frame, valid_mask=mask)` accepts a Boolean mask for invalid sensor/rectification pixels, requiring all four bilinear neighbours to be valid.

`ms` advances **model time**; this interface does not establish real-time speed or camera/model synchronization. The bounded static-image command implements the same pipeline, saves observations and a simulated response trace, and invokes no drone:

```sh
python -m flyvisionbridge.flydrones_run --brain malecns.npz --image rectified_rgb.png --intrinsics intrinsics.json --eyes both --model-ms 1000 --frame-ms 50 --output outputs/flydrones-image
```

An optional `--config config.yaml` supplies upstream dynamics/outputs; its inputs are replaced. `--head-from-camera rotation.json` supplies a JSON 3×3 rotation. Choose a new output directory for each run.

## Replace the pair in an existing Pilot

```python
from flydrones.runtime import Pilot
from flyvisionbridge.flydrones_bridge import install_l2_bridge

# brain and cfg constructed as above; drone is supplied by your application.
pilot = Pilot(brain, drone, cfg, gestures=None, webcam=None)
encoder = install_l2_bridge(pilot, k)
# On a later pilot.tick, input comes from drone.frame().
# encoder.last_drive holds the per-ID validity/status record.
```

Both `Retina` and `InputEncoder` must be replaced: upstream `Retina` discards the original image after reducing it to grids. Upstream `Pilot.webcam` is used for gestures/display, **not** the neural camera input. The hook rejects gesture/overlay webcam configurations so it cannot silently sample the wrong image. A direct webcam experiment should use the Frame/Brain API above, or explicitly supply its images through `drone.frame()`.

The hook itself only installs Python objects; it does not tick, connect, take off or send a command. The actual upstream `Pilot.tick` retains its normal command-sending behaviour. This work qualifies the software input path, not a physical flight controller; integration tests use a non-actuating test object.

## Unknown input has a status, not an invented observation

`drive.rates` is a dictionary of finite `float32` arrays in the **current connectome group's exact index order**. `drive.channels` and `drive.valid` have matching order. Preserve both alongside any results:

| Status | Meaning | Rate sent to native Brain |
|---|---|---|
| `OBSERVED` | Valid camera sample at the published direction | Selected engineering rule |
| `MISSING_DIRECTION` | Published ID exists but its direction is unresolved | 0, with null brightness and false validity |
| `OUTSIDE_CAMERA_FOV` | Direction cannot be observed by this camera | 0, with null brightness and false validity |
| `INVALID_PIXEL_MASK` | Required sensor/rectification pixels are invalid | 0, with null brightness and false validity |
| `UNKNOWN_BODY_ID` | This group's ID is absent from the selected mapping | 0, with null brightness and false validity |
| `NO_FRAME` | Caller passed `None` for the current frame | All external L2 drive cleared |

FlyDrones has no per-input missing-data channel. Zero is therefore a **transport-level abstention**, not biological silence; the network still has its internal state, recurrence and any configured bias. The validity sidecar remains outside the simulator. Upstream also sends zero for a dropped frame, so clearing a dropped frame is not claimed as a unique improvement.

Wrong-eye joins, duplicates, incompatible group types, invalid geometry and changed identities/groups raise errors. Rebuild the encoder after deliberate graph/group reordering. The adapter does not infer receptor mapping for unrecognised graphs or silently keep previous input on an explicit missing frame.

## Replay an existing calibrated screen experiment

With the analysis extra and your own complete `calibrated_temporal_v1` run:

```sh
python -m pip install -e ".[analysis,flydrones]"
python -m flyvisionbridge.flydrones_comparison --recorded-run PATH_TO_RUN --output outputs/flydrones-recorded
```

Required inputs: `rgb.avi`, `capture.json`, `display_log.json`, `frozen_response_lut.json`, and `calibrated_temporal_samples.npz` from the existing [screen analysis](../camera_lab/biomapping/analyze_calibrated.py). The replay verifies cohort/calibration identity, runs both encoders on the same raw frames and uses prior optical phase labels/marker registration. No LUT is applied to either encoder and no time offset is fitted. Only aggregate metrics and hashes are written. The archived result uses a private prior capture; synthetic checks are reproducible entirely from this repository, the private recording is not.

## Attribution

FlyDrones supplies the simulator and native grid frontend (MIT). Reiser lab / MaleCNS supply cell/column identities; Arthur Zhao / Reiser lab's `eyemap-archive` supplies viewing directions. Our contribution is the camera/identity adapter, explicit unknown handling, reproducible comparisons and integration tests. The biological tables and brain simulator are upstream work. See [sources](sources.md), [third-party notices](../THIRD_PARTY_NOTICES.md), and the data-specific GPL/CC-BY/CC-BY-SA terms; original adapter code is MIT.
