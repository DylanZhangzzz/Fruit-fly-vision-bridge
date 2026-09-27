# FlyDrones published-column adapter: comparison report

Date: 2026-09-27. [Integration guide](../../docs/flydrones.md) · [Machine-readable results](summary.json) · [Protocol](../../flyvisionbridge/flydrones_protocol.json).

**Result:** the adapter preserves the published L2 spatial address when neuron storage order changes, and carries explicit observation status into the input log. It successfully supplies native FlyDrones `Brain.tick` and can replace the `Retina`/`InputEncoder` pair in `Pilot`. These are engineering results; this experiment does not establish true L2 receptive fields, neural response fidelity or flight performance.

## Comparison boundary

Upstream: [FlyDrones commit 3e269346b3882c291d2a977bc2c2c6a9c9213c21](https://github.com/SpikeCalls/FlyDrones/tree/3e269346b3882c291d2a977bc2c2c6a9c9213c21). Its native encoder distributes each group's neurons across an eye grid **in array-index order**. The stock configuration mainly drives R1–R6, T4/T5 and other pathways, not L2.

For this comparison, **both methods are explicitly configured with the same 1,779 MaleCNS L2 IDs, the same eye assignments and the same positive brightness × 120 Hz rule**. Native Retina/InputEncoder code is unmodified. The original order is ascending numerical body ID, followed by three declared shuffles. We compare the upstream mapping algorithm applied to L2 with the new adapter; we do not compare the stock complete FlyDrones controller with a complete replacement controller.

The spatial fixture has empty synthetic connectivity. It supplies real identities, not a real brain graph. Actual upstream Brain/Pilot integration tests use a smaller synthetic graph; **full native MaleCNS connectivity has not been qualified through this adapter**. The earlier BrainCPU full-model replay is a separate backend and is not counted here.

## Synthetic position and repeatability checks

Inputs are two independently generated 8-bit grayscale ramps spanning codes 32–223 across a 640×480 image. Camera intrinsics assume 90° horizontal FOV and an explicit bench mounting. A second implementation converts the published azimuth/elevation directly to expected image coordinates without calling the adapter's ray projector. This checks consistency with the published map, **not an independent biological ground truth**.

| Measure | Native index-grid method on L2 | Published-column adapter |
|---|---:|---:|
| Same visible IDs scored | 446 | 446 |
| Median position error, camera pixels | 196.282 | 0.823 |
| 95th percentile error, camera pixels | 360.527 | 1.507 |
| IDs within 2 camera pixels | 0 / 446 | 446 / 446 |
| IDs whose input changed after shuffle, seed 17 | 1,745 / 1,779 | 0 / 1,779 |
| IDs whose input changed after shuffle, seed 29 | 1,751 / 1,779 | 0 / 1,779 |
| IDs whose input changed after shuffle, seed 53 | 1,743 / 1,779 | 0 / 1,779 |
| Largest same-order repeat difference, 3 repeats | 0 Hz | 0 Hz |

Position is decoded from ramp intensity. The adapter's remaining <2 pixel discrepancy includes 8-bit ramp quantization; it is not a measurement of biological angular accuracy. The native grid frontend resizes, blurs, averages cells and divides the image into halves; the adapter takes a bilinear sample at each published ray. The comparison intentionally measures those distinct input mappings, not equivalent optical footprints. The three constant-gray controls differ by at most 0.0111 engineered Hz, consistent with numerical frontend differences rather than a polarity/gain mismatch.

The index-grid mapping is deterministic with fixed ordering too. The adapter's added property is **invariance of a real body's stimulus under reordering/subsetting**, rather than improved same-order determinism.

## Unknown and dropped input

Of the 1,779 IDs, this synthetic geometry observes 446, leaves 1,248 outside the field of view, and retains 85 missing published directions. A Boolean invalid-pixel mask covering the left image half marks 224 of the observed channels invalid and leaves 222 observed. It does not treat masked pixels as dark stimuli.

On an explicit missing frame, **both encoders produce zero external rates**. The new adapter additionally distinguishes `NO_FRAME`, `MISSING_DIRECTION`, `OUTSIDE_CAMERA_FOV`, `INVALID_PIXEL_MASK` and `UNKNOWN_BODY_ID` from observed black. These statuses live in a sidecar because native `Brain.tick` accepts rates only. Zero transport input is not an observation of biological silence and does not reset network recurrence or bias.

## Previously recorded D435 screen replay

Both methods processed the same **1,728 raw RGB frames** from the previously accepted screen experiment. We retained all **21 right-eye L2 IDs** selected by its preceding frozen calibration; no IDs were selected after examining this adapter's results. Optical phase labels and marker-based screen registration came from the existing analysis. The bars and markers had been generated independently of the new adapter. No per-ID LUT was applied to either encoder, and no time offset or amplitude gain was fitted.

| Measure | Native index-grid method on L2 | Published-column adapter |
|---|---:|---:|
| IDs detecting the right-moving bar | 5 / 21 | 21 / 21 |
| IDs detecting the left-moving bar | 5 / 21 | 21 / 21 |
| Correct right-moving passage order on the **same 10 pairs** | 40% | 100% |
| Correct left-moving passage order on the **same 10 pairs** | 40% | 100% |
| Median pairwise timing error, same pairs, right-moving | 1.15015 s | 0.00603 s |
| Median pairwise timing error, same pairs, left-moving | 1.15166 s | 0.00591 s |

The paired comparison uses the intersection of five IDs detected by both methods (10 pairs). Missing detections remain in the 21-ID coverage denominator. The JSON also reports the adapter's 208 distinguishable pairs across all 21 detected IDs: 100% passage-order consistency in each direction, with median pairwise timing errors 0.00838 s and 0.00778 s. Pairs are not independent biological replicates; these are descriptive statistics, not significance tests.

Expected time differences come from marker-registered published positions and the known bar speed. This removes a common time offset rather than fitting one per encoder. The millisecond values describe weighted passage centroids over many ~60 Hz frames, **not sub-frame camera timing precision or neural latency**. Different frontend footprints and RGB luminance weights remain; camera codes are not calibrated radiance.

This is **retrospective replay of a private recording**, not a fresh independent capture. The recorded run is right-eye only. Its geometry targets the published map, so this cannot independently establish that each biological L2 cell really has the assigned receptive field. Recording and calibration hashes are in `summary.json`; raw video, device serials, private paths and per-frame observations are excluded. The synthetic comparison is reproducible entirely from repository data; this private recorded result is not.

## Reproduce and audit

```sh
python -m pip install -e ".[flydrones]"
python -m flyvisionbridge.flydrones_comparison --output outputs/flydrones-comparison
python -m unittest discover -s tests -p test_flydrones_bridge.py -v
```

Optional private recording replay and static image → native Brain commands are in the [integration guide](../../docs/flydrones.md). CI installs the optional upstream dependency and runs the integration tests rather than silently skipping them. Tests check the actual upstream APIs, seeded network repeatability, input clearing, per-ID ordering, side/type mismatches, absent mappings, invalid masks, geometry and a saved-image command through native NPZ loading.

Protocol history is explicit in the JSON. An initial run stopped because its availability check incorrectly required 30 frames from a baseline that lasts only 0.4 seconds (~24 frames). Revision 1.1 separated baseline availability (10 frames minimum) from the moving-bar minimum (30). After seeing the unequal detection coverage in 1.1, revision 1.2 added the common-detected-ID comparison above; response detection thresholds and stimuli did not change. This is a versioned engineering evaluation, not preregistered research.

## What this contributes and what remains

The reusable contribution is an identity-preserving camera input component with explicit abstention and a tested FlyDrones interface. The comparison demonstrates why array order alone is insufficient for transferring published L2 positions into another runtime. The component can save an integrator from implementing that join, eye handling, missing-data policy and validation themselves.

Still open: a fresh, independently recorded binocular screen experiment; qualification with a native full MaleCNS graph; physiological validation of the luminance-to-drive rule; additional cell types and dynamic visual pathways. No improved intelligence, flight performance, stereo reconstruction or full biological equivalence is claimed.

## Attribution and reuse

FlyDrones' native frontend and simulator are upstream work (MIT; [preserved notice](../../LICENSES/FlyDrones-MIT.txt)). Published column/identity inputs are credited to Reiser lab / MaleCNS; viewing directions to Arthur Zhao / Reiser Lab's `eyemap-archive`. The archive requests Zhao et al. 2022 and Nern et al. 2025 citations; see [sources](../../docs/sources.md).

Our original adapter, tests and prose are MIT. These scores are derived from the attributed mapping collection: preserve the source-specific GPL-3.0 ID/column, CC BY 4.0 identity metadata, and CC BY-SA 4.0 archive-direction notices described in [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md). Direction-derived numerical results retain the archive attribution/share-alike terms; no component is offered under a choice of those licenses. Synthetic inputs are ours; private recordings are not redistributed. Source authors do not endorse these results.
