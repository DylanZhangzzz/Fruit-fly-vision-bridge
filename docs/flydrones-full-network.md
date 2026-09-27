# Run and qualify the full native MaleCNS network

The published-column adapter has now been exercised with **166,700 neurons and 10,520,377 directed connections** in the pinned native FlyDrones LIF runtime. This uses the upstream default minimum of **3 synapses per connection**, with no neuron-core/subgraph reduction. It is a full *filtered* native graph, not every segment/weak connection in the raw dataset. [Results, negative controls and remaining limits](../reports/flydrones-full-network/README.md).

## Install and build

Python 3.11+, Git, and an activated environment are required. Allow about **1.11 GB** for the official input tables, additional space for the native graph/results, and several GB of RAM during construction. Do not confuse this native `.npz` with the separate Xenova BrainCPU model format.

```sh
python -m pip install -e ".[full-network]"
python -m flyvisionbridge.flydrones_data --data-dir outputs/malecns-v1-tables --out outputs/malecns-v1.npz
```

The command downloads the three official [MaleCNS v1.0 tables](https://male-cns.janelia.org/download/), invokes the unmodified pinned FlyDrones builder, and applies the **side-metadata compatibility correction below**. Downloads are pinned to object generations and SHA-256 values in [the source manifest](../flyvisionbridge/flydrones_network_sources.json). GCS MD5/size and local SHA-256 are checked, including for cached files. Missing/replaced generations fail explicitly. Failed partial downloads remain for inspection; choose a fresh data directory or remove only the named failed `.partial` file before retrying.

The native graph and `.provenance.json` are written locally under ignored `outputs/`. Use a fresh output filename on subsequent builds. Original official data files and installed upstream source remain unchanged. The data are CC BY 4.0, credited to FlyEM / HHMI Janelia, Cambridge, MRC LMB and Google Research.

`--min-synapses` is explicit and defaults to 3. Changing it changes the graph and requires a new report; the recorded qualification does not cover a different threshold. Native NT signs, annotation filtering and autapse exclusion are retained from the pinned upstream builder. Unknown transmitters keep the upstream default positive sign, which is a model assumption.

## Why a side-metadata correction is required

In FlyDrones commit `3e269346b3882c291d2a977bc2c2c6a9c9213c21`, the builder chooses the **rootSide column** before the somaSide column. In the official annotation table, all 1,779 L2 neurons have missing rootSide and explicit somaSide values. The native output therefore has no L2 members in the requested L/R groups, despite containing all the IDs. Our earlier synthetic wiring fixture supplied sides directly and did not expose this raw-data boundary.

The compatibility step joins official annotations **by body ID**, checks cell types, preserves explicit L/R rootSide values, otherwise uses explicit L/R somaSide, and leaves unknown/midline rows unassigned. It does not infer side from the eye map. It changes side metadata for 148,794 retained neurons: 148,266 use somaSide fallback, with additional missing/midline normalization. The entire final inventory uses 17,492 rootSide assignments, 148,266 somaSide assignments and 942 unassigned rows. L2 becomes **886 left + 893 right**, exactly matching the published mapping inventory.

The builder records content hashes before and after this step for the sparse weights, body-ID order and cell types; they must be unchanged. Group memberships are then rebuilt. This is a local compatibility layer, not an upstream merge or alteration to LIF equations. `--side-policy upstream-column-only` reproduces native metadata for diagnosis; it does not qualify for our full L2 run.

## Run the hardware-free full-network protocol

```sh
python -m flyvisionbridge.flydrones_network --brain outputs/malecns-v1.npz --output outputs/full-network
```

The runner checks graph/provenance identity and all 1,779 L2 ID/type/eye assignments, then uses a persistent Brain within each case and a fresh equal seed between cases. The [protocol](../flyvisionbridge/flydrones_network_protocol.json) fixes the stimulus, 0.5 ms integration step, 50 ms frame holds and 120 Hz maximum engineered darkness drive. It disables tonic flight bias and membrane noise to isolate the external input. Original LIF parameters and graph weights are otherwise retained.

Cases: white/zero drive; a bilateral dark pulse and exact repeat; independent left/right input ablations; a spatial pattern and within-eye shuffled assignment; an explicitly disconnected control with the same full neuron inventory; and a continuous 5 model-second moving-bar sequence. Unknown/out-of-view values never acquire external drive. The shuffle preserves each eye's rate multiset and valid-ID support. It is a negative control, not a model of biological rewiring.

Outputs:

- `summary.json`: graph/source hashes, side correction, identity checks, state/count hashes, group/type aggregates, output-neuron responses, timing and sampled process memory.
- `ticks.csv`: aggregate input and simulated spike counts at each model tick; no images or private paths.
- `per_neuron_totals.npz`: local analysis arrays; excluded from the public repository.

Failed checks remain in the report and return a nonzero exit code. `PASS_ENGINEERING_CHECKS` means the stated software/causal controls passed; it does not mean the model has validated perception, physiology or behaviour. Default motor-output groups are reported even when their spike counts are zero.

## Optional existing-camera replay

Install OpenCV through the analysis extra and point at an existing calibrated screen run:

```sh
python -m pip install -e ".[analysis,full-network]"
python -m flyvisionbridge.flydrones_network --brain outputs/malecns-v1.npz --recorded-run PATH_TO_RUN --output outputs/full-network-recorded
```

Required files are `rgb.avi`, `capture.json`, `display_log.json` and `calibrated_temporal_samples.npz`, produced by the earlier screen workflow. The runner begins at the first optical phase-27 frame and replays 6.5 seconds. At each 50 ms model tick it holds the latest **past** camera frame; future frames are never selected, and frames older than 100 ms explicitly clear input. The original timestamp and camera intrinsics travel with the Frame. Phase labels align the replay interval, not neural latency.

The published example consumes the existing private D435 recording. It does not turn on a camera or send drone commands. This is not a new binocular hardware experiment: both sets of published rays use the same RGB frame, and the earlier independent screen calibration cohort was right-eye only. Depth/IMU are not injected into L2 in this test. A live source can use the same Frame/Brain interface in [the adapter guide](flydrones.md), but the timing measurements here do not qualify end-to-end live camera latency.

## Validation and scope

```sh
python -m unittest discover -s tests -p "test_flydrones*.py" -v
python scripts/run_checks.py
```

The full `run_checks.py` also requires the analysis and camera extras. CI exercises side fallback through the real upstream builder using tiny generated Feather fixtures; it checks integrity failures, unchanged weight content, causal frame selection, input controls and the real runtime APIs. CI does **not** download or execute the large connectome. The full-network results are from the separately documented local run.

The input-rate rule remains an engineering assumption. In the fixed no-bias experiment, signals reach multiple downstream visual cell types but the selected DNg02/DNp03/DNp01 output groups remain silent. This is retained as a negative result, not adjusted away by tuning bias or drive strength. Physiological validation and behavioural readout are separate open tasks.
