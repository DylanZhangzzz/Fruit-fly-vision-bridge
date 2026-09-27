# Binocular mapping and full-model replay

This report uses the published **left-eye** ID/column workbook and **left-eye**
angle output. The right-eye map is unchanged. The complete inventory contains
886 left and 893 right L2 IDs; 847 on each side have joined directions. The other
85 remain unknown (left: 32 missing directions + 7 missing assignments; right:
46 missing directions).

[validation.json](validation.json) contains aggregate results from replaying a
previously captured BRIO frame. No new camera acquisition took place for this
report. The source image was the private first RGB frame from the historical
run `20260927-162727-345607`; it is not redistributed. Projection used the
explicit provisional 90° horizontal FOV and default forward mount. It observed
**229 left and 217 right L2 inputs**. The unchanged full BrainCPU graph contains
166,700 neurons and 25,582,938 edges; model hashes are recorded in the JSON.

Each row below starts from the same model state and random seed and holds the
selected real-image-derived inputs for 100 ms of model time:

| Directly addressed eyes | Input-neuron spikes | Downstream spikes | Downstream with connections off |
|---|---:|---:|---:|
| Left only | 1,310 | 1,126 | 0 |
| Right only | 1,474 | 1,821 | 0 |
| Both | 2,784 | 2,947 | 0 |

Zero-input controls produced zero activity in all three cases. Left → right →
both → empty → both updates retained consecutive model ticks. Wrong-eye labels
were rejected without advancing the model. In single-eye controls, the other
eye has no direct drive; network-mediated activity on the other side is allowed
and is classified as downstream, not as accidental direct input.

[synthetic.json](synthetic.json) repeats the model controls using a reproducible
640×480 white image with its left half black. The unit tests additionally check
that flipping this image reverses the side contrast, unknown samples do not
generate drive, left/right IDs are disjoint, official CSV and XLSX directions
agree, and all 850 author left-column ray stimuli select their own direction.
No spatial test establishes biological receptive-field accuracy independently.

Reproduce from a checkout with the analysis dependencies and the optional model:

```sh
python -m camera_lab.biomapping.import_left_eye
python scripts/run_checks.py
python scripts/validate_binocular.py --assume-hfov 90 --model-dir PATH_TO_MODEL --output outputs/binocular-synthetic.json
```

Use `--image YOUR_FRAME --intrinsics YOUR_INTRINSICS` for a saved real image.
Raw images and per-neuron camera values are excluded from this public report.
The single camera is a shared viewpoint, not measured two-eye stereo geometry.
This verifies engineering addressing and propagation, not biological response
amplitudes, a calibrated view angle or all retinal/visual pathways. See
[the binocular guide](../../docs/binocular.md) for live commands and limitations.
