# Camera-on-screen temporal experiment

Run from the project root:

```powershell
python camera_lab/biomapping/screen_experiment.py
```

Open http://127.0.0.1:8769/ on the screen seen by the D435i. Keep all four
markers visible, fix camera pose and monitor brightness, then click start.
No physical target size is required for this temporal experiment. This does
not recalibrate the biological eye map or change device calibration.

The recorder retains every unique 640x480 RGB frame requested at 60 Hz in
lossless FFV1 video, with actual frame timestamps. It retains IMU samples and
one depth image per second as auxiliary measurements. Camera exposure and
gain are fixed during acquisition and previous options restored on exit.
Capture automatically ends after the browser sequence or a 45-second timeout.
The localhost server stays idle between acquisitions; it does not leave the
camera streaming. No images leave this computer.

The optical phase labels, fixed black/white patches and fiducials are read
from camera pixels. Reported camera code values are not calibrated radiance.
Homography RANSAC uses a 6-pixel threshold in the 1000x700 canonical plane,
approximately two image pixels at the present camera scale. The geometry
test checks this against a known synthetic perspective warp. Invalid frames
and unobserved neural channels remain unknown rather than black input.

Analysis reports measured camera cadence, frame loss, optical screen
coverage, observed phase IDs, 100 ms flashes, sine-fit R² for 1/2/4 Hz and
dark-bar passage order at three screen positions. A frozen published L2
recurrent model consumes measured per-ray intensity contrast, causally held
between frames and integrated with <=1 ms substeps. Integration substeps do
not recover camera information that was never sampled. The initial baseline
is fixed to the initial gray screen; adaptation and spatial surround are not
implemented. Output is effective voltage in arbitrary units, not mV or Hz.
No new brain injection is performed.

Browser RAF timing records rendering requests only. Do not compare its
clock directly with camera hardware time or infer absolute latency. Phase
bits are at a different image row than the stimulus, so panel scanout and
rolling shutter can affect transitions. 60 Hz does not establish 13 ms
physiological dynamics or faithfully measure a 20 ms flash. L2 response
traces here are predictions; biological validation remains the separate
published-data comparison in temporal_validation/.

Re-run analysis and implementation checks:

```powershell
python camera_lab/biomapping/analyze_screen.py <run-directory>
python camera_lab/biomapping/test_screen_experiment.py
```

The initial 20260927-125025-927706 recording contains the static screen after
a browser animation startup error. It has no valid sequence log and must
not be treated as a successful stimulation experiment. Its raw data is
retained for audit. The startup error was corrected by clamping the first
RAF elapsed time to zero and using the latest phase start for lookup.

## Same-location gray transfer experiment

Open http://127.0.0.1:8769/photometric.html on the physical screen facing the
camera. The button requests fullscreen and records a 42.2-second sequence:
32 randomized training gray codes, 16 withheld intermediate codes, and eight
repeat anchors. The split and order are fixed before acquisition. Each gray
stage lasts 0.7 seconds, with an initial and final gray baseline. The separate
three-second preview overlays mapped L2 rays: green in the stimulus area,
yellow outside it. This does not alter the biological map or mount transform.

Phase labels use sequential Gray code (one changing bit), optically decoded
from adjacent complementary black/white pairs. Each pair difference must
exceed 20 camera code values; this avoids a shared off-region threshold.
Low-confidence/unknown labels are rejected. Analysis uses
the longest contiguous optical run per stage and removes four camera frames
from each edge, with at least 12 retained samples required. These exclusions
reduce display scanout, rolling-shutter and phase-transition contamination.

Nine screen locations and each sufficiently observed mapped L2 ray get a
separate monotone lookup table fitted ONLY to training medians. Acceptance
requires all 32 training stages, 16 holdouts and eight repeats; maximum
holdout and repeat errors must each be <=5% of the same-location measured
camera range, which must span at least 30 camera code values. These are
predeclared engineering tolerances, not physiological criteria. Near-flat
intervals are explicitly reported as unreliable to invert.

This measures the combined **screen-code to camera-code transfer**. It does
not identify display and camera gamma separately, measure linear physical
luminance, or calibrate photoreceptor/neuronal response. An inverse lookup
gives only an equivalent screen digital code within its measured range.
Black/white values from the same location avoid the old off-region spatial
reference mismatch. Changes to exposure, pose, screen brightness or ambient
light require revalidation. No full-brain input is replaced automatically.

Artifacts include raw lossless video, RGB timestamps, depth and IMU records,
the actual display log, per-channel phase medians/MADs, train-only lookup
tables, held-out/repeat errors and a report plot. Reanalyze with:

```powershell
python camera_lab/biomapping/analyze_photometric.py <run-directory>
python -m unittest discover -s camera_lab/biomapping -p 'test_*.py'
```

The first gray run, `20260927-134618-286627`, did not pass: only 29 of 32
training phases retained enough contiguous samples, and no mapped L2 rays
were in its stimulus region. Its data and failure report are retained. The
revised complementary phase pairs and longer dwell were fixed before the
next recording, without changing error acceptance thresholds.

`20260927-135311-544262` passed with 2,521 frames at 59.53 Hz and no recorded
frame gaps or queue drops. All nine screen ROIs and 23 sufficiently observed
L2 channels passed. Worst L2 held-out error was 1.0152% of local camera range;
worst repeat deviation was 0.9439%. Six ambiguous optical-code frames were
excluded. Forty-three depth images and 11,095 IMU samples were retained.
Near-flat dark intervals remain unsuitable for reliable inverse decoding.
The device did not provide per-frame exposure/gain metadata; the report
retains requested/read-back SDK settings, without claiming framewise proof.

## Frozen-calibration temporal holdout

`/calibrated_temporal.html` starts a separate prospective experiment using
the already accepted `20260927-135311-544262` lookup tables. The server copies
the exact LUT and stimulus into the new run and records the LUT hash before
streaming. The experiment uses screen codes 112/160/208, eight 200 ms flashes,
1/2/4 Hz sine modulation (160 +/- 48), and left/right moving dark bars. No
response table is refitted from temporal validation data. Every ROI and L2
uses its own original table. Flat intervals and extrapolation remain NaN.

`analyze_calibrated.py` fixes acceptance limits before capture: static code
error <=5; sine R² >=0.95 and amplitude error <=10%; flash width error <=60 ms;
signed motion-passage correlation >=0.9 and residual <=100 ms. Calibration
intrinsics/settings must match; 95th-percentile screen marker displacement
must be <=3 camera pixels. IMU stationarity checks use vector deviations from
the run median with p95 <=0.04 rad/s (gyro) and <=0.25 m/s² (acceleration), over
a coarse host-receipt interval. These are engineering limits. The checks do
not calibrate IMU orientation, establish exact RGB/depth/IMU synchronization,
or certify screen depth. Depth remains auxiliary saved data.

L2 model input is **equivalent screen-code contrast**, `(code-160)/160`,
not calibrated physical luminance contrast. Outputs and polarity checks are
conditional model predictions, not neuronal measurements or spike rates.
Sine phase is fitted independently, so no absolute-latency claim is made.
Dark-bar passage checks validate position order, not L2 direction selectivity.
The tool reports failed criteria rather than relaxing limits after a run.

The first prospective run, `20260927-140733-348065`, correctly failed reuse
of the earlier calibration: screen-marker displacement p95 was 22.23 pixels,
central static gray error reached 18.97 codes, and some calibrated neural
sampling rays no longer lay in the stimulus. There were no frame/queue gaps;
IMU stationarity and all eight flash durations passed. This is retained as
a failed calibration-transfer result, not relabeled as a successful run.

Subsequent gray calibration records all supported color controls including
manual white balance, gamma, brightness, contrast, saturation and sharpness.
The calibrated temporal recorder reapplies those exact recorded controls
and verifies their read-back values, in addition to exposure and gain.
This addresses session-to-session color processing differences; it does not
establish calibrated radiance. Camera options are restored after capture.

## Continuous canvas and independent drift references

Use `/continuous_validation.html` for the complete current workflow. It keeps
one fullscreen canvas through calibration, analysis and the independent
temporal recording. Every RAF log now records the actual canvas rectangle
and viewport. Explicit automatic height preserves the canvas aspect ratio.
The calibration table is finalized before the temporal recorder starts.

The uncorrected continuous pair `20260927-141819-230992` (calibration) and
`20260927-141919-303142` (temporal) verified that geometry could remain stable
(p95 marker displacement 0.36 px) while the camera brightness scale changed.
Flash widths, both motion directions and conditional model step polarity
passed; absolute static gray decoding failed. Their failure reports remain.

The next prospective version applies an affine correction from independent,
fixed black and white screen patches before querying each frozen local LUT:

`aligned = calibration_black + (camera - current_black) *
(calibration_white - calibration_black) / (current_white - current_black)`

Calibration reference medians are stored in the LUT. Current references come
from the same captured frame, so no future frames or test target gray values
enter the correction. Reference contrast must exceed 20 camera codes; gain
ratios outside 0.8–1.25 are rejected. The original static, sine, flash and
motion acceptance limits remain unchanged. Corrected and raw camera values,
reference samples and correction gains are all retained in the NPZ output.
An exploratory replay motivated this method; acceptance requires fresh data.

This correction requires the fixed optical reference patches to remain in
view. It has not been validated for arbitrary natural scenes without such
references, and it still does not produce physically calibrated luminance.

Fresh prospective validation `20260927-142451-807004`, using calibration
`20260927-142351-829513`, passed all unchanged engineering limits with the
reference correction enabled. It retained 1,728 frames at 59.53 Hz with no
frame or queue gaps. All 21 L2 IDs (20 distinct columns) and nine ROIs passed;
worst L2 static error was 3.828 gray codes, minimum sine R² was 0.99551, and
maximum sine amplitude error was 5.57%. All eight flashes and both bar
directions passed. Marker displacement p95 was 0.382 camera pixels and IMU
stationarity checks passed. Median independent reference gain correction
was 1.03375. The LUT was frozen before acquisition and remained byte-identical
to its calibration artifact; no temporal target values were used to refit it.

Earlier uncorrected recordings are preserved, including the layout-corrected
but brightness-drifted `20260927-141604-245055`. Passing this controlled screen
experiment does not validate real neural responses or unreferenced natural
scenes. The server releases the camera after each bounded recording.
