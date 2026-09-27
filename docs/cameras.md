# Camera inputs

## D435i: recorded experimental path

Install `.[analysis,camera]`, connect exactly one D435i over USB 3, and close applications using it. With several devices, select one explicitly:

```powershell
$env:FLYVISION_REALSENSE_SERIAL = 'YOUR_DEVICE_SERIAL'
python camera_lab/biomapping/capture_multimodal.py
```

On Linux use `export FLYVISION_REALSENSE_SERIAL=YOUR_DEVICE_SERIAL`. The capture warms up for 2 seconds, records approximately 5 seconds, saves RGB/depth snapshots at roughly 5 Hz plus native-rate IMU, then releases the camera. This bounded snapshot path is for geometry, not millisecond temporal response validation. Outputs are under the ignored `camera_lab/biomapping/captures/` directory. Reports contain local device metadata; review before sharing.

```sh
python camera_lab/biomapping/run_reference.py PATH_TO_CAPTURE
# Optional BrainCPU-backed MaleCNS snapshot controls:
python camera_lab/biomapping/run_malecns.py PATH_TO_CAPTURE
```

The **screen experiment** separately requests 60 Hz RGB, 30 Hz depth with 1 Hz depth storage, and native-rate IMU:

```sh
python camera_lab/biomapping/screen_experiment.py
```

Open `http://127.0.0.1:8769/continuous_validation.html` on the display seen by the camera. Keep all four markers and the black/white patches visible, fix camera pose/display brightness, and start from the UI. It records a gray calibration followed by a separate frozen-LUT temporal experiment. The server starts idle; acquisition is bounded and restores camera options. Stop the server with Ctrl+C after a recording has finished. [Protocol details](../camera_lab/biomapping/screen_experiment/README.md) retain failures and acceptance thresholds.

The standalone `calibrated_temporal.html` requires `?calibration=YOUR_ACCEPTED_RUN_DIRECTORY`; it has no preset local recording. Prefer the continuous workflow for a new setup.

The exact recorded sensor profiles require D435i-compatible motion streams. D435 without IMU and other depth cameras are not supported by this recorder unchanged; they can use the RGB-only route or implement the frame contract below. Do not invent missing IMU/depth data.

## Saved images and ordinary RGB webcams

Provide intrinsics for the **actual rectified image resolution**. Example JSON (numbers below are demonstrative, not a calibration for your camera):

```json
{"width":640,"height":480,"fx":600,"fy":600,"ppx":319.5,"ppy":239.5,"coeffs":[0,0,0,0,0]}
```

```sh
python -m flyvisionbridge.cli --image frame.png --intrinsics my_intrinsics.json --output outputs/image-01
python -m flyvisionbridge.cli --camera 0 --intrinsics my_intrinsics.json --output outputs/webcam-01
```

The webcam path requires OpenCV (`.[camera]` or `.[analysis]`), captures one frame, converts BGR to RGB, and releases the device even on failure. It records host receipt time, not exposure time. OpenCV hardware capture is implemented but **not yet physically validated in this project**. Nonzero distortion coefficients are rejected; rectify the image and update intrinsics before using this route. Focus/zoom/crop/resolution changes can invalidate intrinsics.

`--head-from-camera rotation.json` supplies a proper 3×3 rotation from camera coordinates into head coordinates. Default axes are documented in [mapping](mapping.md); the default is an installation assumption. `--depth depth.npy` accepts only already registered **color-camera Z in metres**, matching the RGB array. Raw depth or SDK-aligned depth must not be passed without verifying its coordinate meaning. This CLI exports sampled values, not BrainCPU firing-rate inputs.

## Adapter contract for other cameras

Use `flyvisionbridge.Frame` and `map_frame`:

```python
from flyvisionbridge import Frame, map_frame
frame = Frame(rgb=rgb_uint8, intrinsics=k,
              timestamp_s=timestamp, clock_domain="device_clock")
result = map_frame(frame)
```

- RGB: `H×W×3 uint8`, RGB order; a rectified pinhole image and matching intrinsics.
- Depth: optional `H×W` float array of color-camera Z in metres; zero/negative/nonfinite values are unknown. Missing depth never erases valid RGB.
- Gyro: optional three finite values in rad/s, already transformed into the color camera frame and associated with this frame. The bridge does not establish synchronization or remove bias.
- Preserve acquisition clocks, units, validity and registration evidence in the adapter's own recording metadata. A host timestamp is not interchangeable with sensor exposure time.

RealSense's SDK extrinsic rotation array is column-major; use `reshape(3,3,order='F')`. Existing replay deprojects native depth, applies depth-to-color extrinsics and uses a nearest-depth buffer. Directly treating aligned native depth as color-camera Z is not equivalent under arbitrary extrinsics.

## Calibration is separate from biological mapping

`python camera_lab/calibrate.py target` generates print/screen chessboards. For a physical calibration use `capture --square-mm MEASURED_SIZE` and `solve SESSION`. A screen square's CSS size is not its physical size; measure it. Camera intrinsics do not determine the fly head frame or the anatomical eye map. IMU calibration requires the documented six-pose protocol; a stationary gravity vector alone cannot determine yaw or a biological head orientation.
