# Roadmap and useful contributions

These are open tasks, not completed validations. Open an issue to agree on a bounded experiment before collecting large datasets or changing scientific claims.

## Priority 1: held-out stimulus prediction

Find compatible public L2 recordings with different flash durations, temporal frequencies or contrasts. Record the original stimulus waveform, timing, indicator, preprocessing, animal grouping and license. A different ROI from the same flash dataset is not a new stimulus condition.

Before inspecting test outcomes, commit a protocol defining:

1. Training and held-out datasets/conditions, selected by whole animal where possible.
2. Frozen dynamic parameters, input conversion, initial conditions, measurement model, latency and preprocessing. Any necessary new sensor calibration must use separate calibration data.
3. Baselines that can predict the new stimulus (e.g. a train-only linear temporal kernel and feedback-free dynamics), plus a constant baseline. A copied mean-flash template is not automatically a meaningful predictor of another duration.
4. Metrics in measurement units, exclusions, uncertainty grouping and a criterion for improvement. Keep failures and parameter-boundary cases.
5. An explicit decision if compatible data are unavailable: predictions may be shown, but cannot be called validation.

Deliverable: downloadable input manifest, frozen protocol, executable benchmark and per-animal report. No webcam experiment can replace missing live-fly response measurements.

## Priority 2: camera and geometry

- Validate the generic OpenCV adapter on actual cameras and document supported formats/resolutions.
- Add another depth-camera adapter with tested depth-to-color registration, units and clock-domain handling.
- Measure IMU bias and video/gyro time offset using independent motion observations; test pure rotation separately from translation.
- Test near/far occlusion and parallax with opaque targets and independent displacement measurements.
- Separate screen/camera transfer from physical radiance calibration, and test scenes without fixed reference patches.

## Priority 3: biological fidelity

- Receptive-field acceptance angles, spatial surrounds, spectral sensitivity and adaptation supported by independent data.
- A defensible observation model from biological dynamics to the measured indicator; never relabel ΔF/F as Hz.
- Independent mapping landmarks or physiological receptive fields, without extrapolating the 46 missing directions merely to achieve 100% coverage.
- Downstream decoding with held-out stimuli, mapping-shuffle controls and multiple initial states/seeds. Treat anatomical connectivity as evidence about structure, not sufficient dynamics.
