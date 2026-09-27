# Archived controlled-screen result

Run: `20260927-142451-807004`; calibration: `20260927-142351-829513`.

`validation_summary.json` preserves the numerical acceptance results, with the local report URL and raw IMU orientation removed. `calibrated_temporal.png` is a scientific plot, not a room photograph. Raw RGB/depth/IMU recordings are not published. This archive can be inspected but cannot recreate the original measured pixels; reproduce the protocol using your own camera and monitor.

Result: PASS_ENGINEERING_TEMPORAL for 21 L2 IDs / 20 unique columns and nine ROIs. Frozen LUT, independent black/white correction, 1,728 RGB frames, approximately 59.53 frames/s, no observed frame or queue gaps. Biological validity and physical luminance calibration remain false.

Failed prior recordings are listed in the summary and discussed in [findings](../../docs/findings.md). Their failures motivated geometry preservation and brightness-drift correction. Acceptance thresholds were not relaxed. The final accepted recording was newly acquired after those changes.

See [screen protocol](../../camera_lab/biomapping/screen_experiment/README.md) and [camera instructions](../../docs/cameras.md).
