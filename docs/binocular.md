# Left-eye and binocular bridge

The live webcam entry now defaults to `--eyes both`. Left and right visual rays
are projected into the same observed camera image independently, then addressed
to their own MaleCNS L2 body IDs. `--eyes left` and `--eyes right` select one eye.
The worker verifies each supplied ID's type and eye against model metadata.

```sh
python -m flyvisionbridge.live --model-dir PATH_TO_MODEL --device-name "Logitech BRIO" --assume-hfov 90 --eyes both
```

Use `--camera 0` for an OpenCV-indexed camera. See [webcam setup](webcam-live.md)
for dependencies, intrinsics, timing and local recording. The dashboard shows
each eye's target and observed counts; blue dots mark left-eye samples and orange
dots mark right-eye samples. Controls now include left-only and right-only drive.
These controls reset the model; normal frame updates preserve its state.

## Published evidence and missing entries

| Eye | Model L2 IDs | Published directions joined | Missing direction | Missing column assignment |
|---|---:|---:|---:|---:|
| Left | 886 | 847 | 32 | 7 |
| Right | 893 | 847 | 46 | 0 |
| Both | 1,779 | 1,694 | 78 | 7 |

Left-eye identity-to-column assignments come from Reiser lab's
[`ME_L_columnar-cells_location.xlsx`](https://github.com/reiserlab/visualpathways/blob/23f6ac131529b5f56894c6eeb9b88b17894fc00d/params/ME_L_columnar-cells_location.xlsx).
Directions come from the author's separate
[`pqxyztp_left.xlsx`](https://github.com/artxz/eyemap-archive/blob/503c7f055d5491a48b60b49ade8c71798d24d8f1/maps/eyemap_mcns_f20240701/pqxyztp_left.xlsx).
The join is exact `bodyId → left-eye (hex1,hex2) → left-eye direction`. It does not
pair cells by row order, copy right-eye IDs, mirror right-eye directions or infer
missing boundary coordinates. The two published direction tables are not exact
mirrors. The left column assignment is checked against model ID/type/side; unlike
the historical right mapping, it does not have a second independent column table.

The minimal L2 inventory is derived from pinned model metadata, with the original
compressed metadata hash retained. It records both eyes and includes the seven
left-eye model IDs lacking an author column assignment. Licenses and attribution
are in [third-party notices](../THIRD_PARTY_NOTICES.md). Four added source/subset
files are covered by the source checksum verifier.

## Reproduce the join and checks

```sh
python -m camera_lab.biomapping.import_left_eye
python scripts/run_checks.py
python scripts/validate_binocular.py --assume-hfov 90 --output outputs/binocular-synthetic.json
# Optional full-model replay of a saved image; does not open a camera:
python scripts/validate_binocular.py --image frame.jpg --intrinsics camera.json --model-dir PATH_TO_MODEL --output outputs/binocular-replay.json
```

The new left product is `camera_lab/biomapping/data/malecns_left_crosswalk.json`;
its provenance and exclusions are in `left_mapping_report.json` beside it.
`load_eye_mapping('both')` returns both eyes. For compatibility, the existing
`load_mapping()` / `map_frame(frame)` and snapshot CLI remain right-only by
default. Use `map_frame(frame, load_eye_mapping('both'))` or
`python -m flyvisionbridge.cli --demo --eyes both --output outputs/demo-both`.
An explicit custom `--mapping` cannot be combined with `--eyes`.

## Validation scope

[The archived validation](../reports/binocular/README.md) includes a previously
captured BRIO image replayed through both eyes in the full graph, a reproducible
synthetic image, independent source checks and eye-switch/state tests. The image
replay at an assumed 90° horizontal FOV observes **229 left + 217 right** inputs.
These counts depend on projection and mounting, not a fixed channel limit.
The new binocular live mode has not yet had a fresh physical acquisition run;
the previous BRIO hardware run used right-eye input only.

A single camera supplies a **common optical origin** to both eye maps. It does
not recover the different left/right eye origins, stereoscopic disparity or
unseen side/back directions. Depth-assisted reprojection from measured origins
or multiple calibrated cameras would be separate work. Both-eye L2 input also
does not implement every retinal/visual cell class. The camera geometry is still
provisional unless calibrated, and `120 × (1 − RGB code brightness)` is still an
engineering input rather than a biologically validated transfer function.
