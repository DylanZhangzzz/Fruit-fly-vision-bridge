# Webcam → BrainCPU hardware evidence

On 27 September 2026, a Logitech BRIO on Windows supplied actual RGB frames to
the complete camera-to-model chain. Capture used FFmpeg DirectShow, 640×480,
30 requested camera frames/s, with five model updates/s. This report covers
that camera/backend combination. OpenCV-indexed capture is implemented but
has not been physically qualified here.

The model was the separate Xenova `fruit-fly-simulation` checkout at
`776d115ee5aa934578a87fd6d260d138084f59c1`, with the unchanged BrainCPU engine,
166,700 neurons and 25,582,938 edges. Exact engine, metadata and manifest hashes
are in [validation.json](validation.json).

| Measurement | Result |
|---|---:|
| Visible, mapped L2 input IDs | 217 |
| Consecutive model updates | 620 |
| Wall-clock capture interval | 123.86 s |
| Model time advanced | 12.40 s |
| Model-time / wall-time ratio | 0.1001× |
| Total simulated spikes | 438,438 |
| Spikes outside directly driven input IDs | 252,608 |
| Model ticks continuous across updates | Yes |
| Mean sampled RGB-code brightness range | 0.2197–0.8187 |
| Host-receipt-to-result age, median / p95 | 47 / 78 ms |
| Skipped camera frames between updates | 3,095 |

The reader drains the camera continuously and the model uses the newest frame.
The skipped frames are not simulated. The reported age is not exposure-to-result
latency. This is a live, continuously updated integration at 0.1× model speed,
not a 1× biological real-time claim.

## Causal software controls

The first captured input was held for 50 ms of model time in each condition,
with identical initial state and random seed:

| Condition | Input-neuron spikes | Downstream spikes |
|---|---:|---:|
| Zero input | 0 | 0 |
| Camera-derived input | 715 | 753 |
| Same input, connections disabled | 715 | 0 |
| Same image, half input gain | 365 | 315 |

These results establish that the captured input drives the selected neurons and
that graph connections carry activity downstream. They do not establish the
biological accuracy of the input conversion.

The operator reported covering and uncovering the lens twice during this run.
The log contains substantial visual-input variation, but has no synchronized
operator event markers: exact occlusion boundaries and the cause of each bright
or dark frame are not certified. Exposure/white-balance remained camera-managed.

For an additional engineering contrast check, the recorded frames with the lowest
and highest mean sampled brightness were selected **after recording**. Each
actual input vector was replayed for 100 ms from the same initial state and seed:

| Recorded input | Mean engineered input | Downstream spikes | Connections disabled |
|---|---:|---:|---:|
| Lowest mean brightness, 0.2197 | 93.64 Hz | 2,729 | 0 |
| Highest mean brightness, 0.8187 | 21.75 Hz | 563 | 0 |

Thus different captured inputs produce different downstream activity with
random seed and initial state controlled. This is a post-hoc two-input check,
not a held-out physiology test or an estimate of a real fly's response amplitude.

## Reproduce

Follow [the live webcam guide](../../docs/webcam-live.md), acquire a new bounded
run, then export aggregate evidence and optionally repeat the contrast control:

```sh
python scripts/export_webcam_report.py outputs/webcam-live/YOUR_RUN --output outputs/webcam-report.json --model-dir PATH_TO_MODEL
```

Raw camera images, per-channel inputs, per-frame private logs and device serials
are excluded from this public report. Numerical replay of this exact private
scene therefore requires the original local recording; others should acquire
their own scene rather than expect identical spike counts. Hardware-free worker
tests use the unchanged upstream engine with an explicitly synthetic tiny graph.

The projection used an **assumed 90° horizontal field of view** and assumed bench
mount orientation, not calibrated BRIO optics or a measured biological head
orientation. The encoder was `120 × (1 − RGB code luminance)` Hz. Depth and IMU
were unavailable; no substitute values were invented. Camera acquisition,
anatomical provenance and biological response validity remain separate claims.
