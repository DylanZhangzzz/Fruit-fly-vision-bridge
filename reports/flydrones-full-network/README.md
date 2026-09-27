# Full MaleCNS runtime qualification

Date: 2026-09-27. [Build/run guide](../../docs/flydrones-full-network.md) · [Summary](summary.json) · [Aggregate tick traces](ticks.csv) · [Protocol](../../flyvisionbridge/flydrones_network_protocol.json) · [Official input hashes](../../flyvisionbridge/flydrones_network_sources.json).

**Result: the camera adapter drives the full filtered native FlyDrones network, with exact bilateral L2 identity and passing engineering controls.** This qualifies execution and causal propagation within this simulator. It does not validate real neuronal responses, visual understanding or behaviour.

## Graph and compatibility correction

The official [MaleCNS v1.0 tables](https://male-cns.janelia.org/download/) were verified against pinned GCS generation/MD5 and local SHA-256. The native builder at FlyDrones commit [`3e269346b3882c291d2a977bc2c2c6a9c9213c21`](https://github.com/SpikeCalls/FlyDrones/tree/3e269346b3882c291d2a977bc2c2c6a9c9213c21) retained **166,700 neurons, 10,520,377 directed connections and 104,351,893 absolute synaptic weight counts**. There is no sensorimotor-core/subgraph reduction. The native minimum of **3 synapses per connection**, annotation filtering and autapse exclusion remain in force. “Full” means this full native filtered graph, not every segment/weak edge in the raw release. It differs from the 25.58-million-edge graph in our separate BrainCPU backend.

The initial native build contained all 1,779 L2 IDs but **zero members in L2_L/L2_R**: the builder selected rootSide at column level, while every L2's rootSide is missing and somaSide contains L/R. The compatibility layer joins official annotations by body ID, preserves explicit L/R rootSide, otherwise uses explicit L/R somaSide, and leaves remaining unknown/midline values unassigned. It does not infer side from the eyemap. This boundary was not exposed by the earlier synthetic wiring fixtures.

The corrected L2 inventory is **886 left + 893 right, with no missing, extra or wrong-eye IDs**. Side metadata changes for 148,794 retained neurons overall. Content hashes before/after confirm identical sparse weights, body-ID order and cell types. Installed upstream source is untouched; the correction is our documented compatibility layer. Detailed origin counts and hashes are in the build provenance embedded in `summary.json`.

## Fixed experiment and controls

Each case starts from the same native initial state and seed `20260927`; state persists across ticks within a case. Configuration: 0.5 ms integration, 50 ms input holds, maximum 120 Hz engineered darkness drive, zero membrane noise, **tonic flight bias disabled**. Disabling bias isolates the camera contribution and differs from the stock flight configuration. The synthetic 640×480 camera assumes 90° horizontal FOV and bench orientation, observing **229 left + 217 right** L2 positions.

Pulse cases last 1 model second: white for 200 ms, black for 600 ms, white for 200 ms. Pattern cases use a dark left image half during that interval. Shuffling only observed IDs within each eye preserves every tick's rate multiset and all unknown/out-of-view zeros.

| Case | Simulated L2 spikes, L / R | Simulated non-L2 spikes | Active non-L2 neurons |
|---|---:|---:|---:|
| Zero input, no noise/bias | 0 / 0 | 0 | 0 |
| Bilateral pulse | 10,613 / 9,644 | 26,589 | 2,408 |
| Same pulse and seed again | 10,613 / 9,644 | 26,589 | 2,408 |
| Left input only | 10,708 / 0 | 12,960 | 1,201 |
| Right input only | 0 / 9,664 | 13,865 | 1,232 |
| Spatial pattern | 9,017 / 1,655 | 14,702 | 1,306 |
| Same rate multiset, shuffled positions | 9,338 / 1,684 | 16,440 | 1,360 |
| Bilateral pulse, all connections disabled | 12,709 / 12,089 | 0 | 0 |
| Continuous moving bar, 5 model seconds | 13,752 / 12,322 | 53,814 | 3,037 |

Repeated pulses agree **exactly in every neuron's per-tick spike count and final voltage/conductance hashes**, not just totals. The disconnected control retains all neurons/equations but has zero weights; it is not counted as a full-connectivity result. Its zero non-L2 spikes confirm that connected activity comes through the network rather than direct downstream injection. Removing recurrence can also change L2 spike counts, so those totals need not match.

Shuffling changes total spike counts at 1,813 neurons, including 1,541 non-L2 neurons. Assignment therefore matters within this simulator; this does not show which response resembles a real fly. Exact identity, unknown-input, finite-state, persistent-clock and unchanged-weight checks all passed. Downstream types include Tm1, Tm2, Tm4, Dm15, Dm6 and T1; type aggregates are descriptive, not selected biological success targets.

**DNg02_L/R, DNp03_L/R and DNp01_L/R remain at zero spikes in every case.** We retain this negative result without tuning bias or drive to create motor activity. It does not establish that those groups are unreachable and does not validate flight control.

## Existing D435 recording

The same full network replays **6.5 seconds / 130 held RGB frames**, starting at optical phase 27. Each 50 ms model tick uses the latest past camera frame. Source age is 0–16.788 ms, with **zero stale ticks** exceeding the 100 ms cutoff. Source indices run from 1,177 to 1,560; intervening unused frames are not neural inputs. This is explicit resampling, not a claim of 60 Hz sensor/model synchronization.

Recorded intrinsics cover **105 left + 93 right** L2 directions. The model generates **217,989 simulated spikes**, including **127,764 at 1,256 non-L2 neurons**, with finite state throughout. Both eyes use the same RGB image; motor outputs remain silent. Depth/IMU are not injected in this test.

This is retrospective execution of a private video, not new live capture or fresh binocular calibration. The earlier independent screen-calibration cohort was right-eye only. Camera inputs and simulated outputs are not neuronal measurements. Public artifacts contain hashes and aggregates, excluding raw frames, serials and private paths. Synthetic/full-network cases use public inputs; reproducing the private-camera result requires that recording or a new compatible experiment.

## Runtime and memory

Local environment: Windows/AMD64, Python 3.12.14, NumPy 2.5.3, SciPy 1.18.1. Measurements are descriptive, not portable performance guarantees.

| Case | Model time | Wall time | Model seconds per wall second |
|---|---:|---:|---:|
| Bilateral pulse | 1.0 s | 0.843 s | 1.186 |
| Continuous moving bar | 5.0 s | 5.256 s | 0.951 |
| Existing-video replay | 6.5 s | 11.507 s | 0.565 |

Case wall time includes mapping/checks, excludes graph/Brain initialization and report writing, and in replay includes decoding the prefix before the chosen interval. Thus replay speed is not live-camera latency. Brain-only and encoding times are separately recorded. Peak sampled runner RSS is **428,539,904 bytes (~409 MiB)** at 20 ms sampling, including load/initialization/cases. Sampling may miss brief peaks; this excludes the separate builder and other applications. Construction needs several GB of RAM.

Profiling found repeated conversion of all numeric IDs to strings. The guard now compares a numeric snapshot while detecting in-place changes. Local moving-bar encoding time fell from 2.763 s to 1.307 s. Every case's input hash, per-neuron per-tick spike hash and final voltage/conductance matched the earlier run exactly. [Equivalence check](optimization_check.json). This is not a controlled cross-machine speed benchmark.

## Reproduce and interpret

```sh
python -m pip install -e ".[full-network]"
python -m flyvisionbridge.flydrones_data --data-dir outputs/malecns-v1-tables --out outputs/malecns-v1.npz
python -m flyvisionbridge.flydrones_network --brain outputs/malecns-v1.npz --output outputs/full-network
```

See the [guide](../../docs/flydrones-full-network.md) for recorded replay and tests. CI uses tiny generated Feather tables to reproduce the side-column bug and test its correction; **the full real graph ran locally, not in CI**. Seeded equality is established in this dependency/runtime environment, not across arbitrary versions. The protocol preceded inspection of network responses; later integrity/reporting additions and ID-guard optimization changed neither stimuli, neural parameters nor resulting states.

Full filtered-network execution is now verified under this protocol. Physiological calibration, held-out neural recordings, fresh live binocular acquisition and behavioural outputs remain open.

FlyDrones supplies the native builder/simulator (MIT). MaleCNS data are CC BY 4.0: FlyEM / HHMI Janelia, Cambridge, MRC LMB and Google Research. Column/identity and viewing-direction resources retain their source-specific terms and Reiser lab / Arthur Zhao attribution. Original tooling/prose are MIT; direction-derived numerical results retain relevant CC BY-SA 4.0 attribution/share-alike terms and [third-party notices](../../THIRD_PARTY_NOTICES.md). No connectivity weights or private images are bundled. Source authors do not endorse these results.
