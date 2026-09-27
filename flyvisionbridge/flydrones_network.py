"""Bounded full-network qualification with explicit zero/disconnect/shuffle controls.

Uses a real native MaleCNS graph supplied by the caller. Outputs are simulated
spikes and input diagnostics, never measured neural activity or drone commands.
"""
import argparse
from collections import Counter
import csv
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import threading
import time

import numpy as np

from .bridge import Frame, load_eye_mapping
from .flydrones_bridge import L2Encoder, l2_config
from .flydrones_comparison import sha
from .live_core import approximate_intrinsics

PROTOCOL = Path(__file__).with_name("flydrones_network_protocol.json")


def array_hash(a):
    a = np.ascontiguousarray(a)
    if a.dtype.hasobject:
        # Hash labels, not process-specific PyObject pointer addresses.
        a = a.astype(str)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()


def weight_hash(graph):
    return {key: array_hash(getattr(graph.weights, key)) for key in ["indptr", "indices", "data"]}


class MemoryMonitor:
    """Sample process RSS, including load/initialization; not system RAM usage."""
    def __init__(self):
        import psutil
        self.process = psutil.Process()
        self.start = self.peak = self.process.memory_info().rss
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        while not self.done.wait(.02):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.done.set()
        self.thread.join()


def synthetic_frames(case, p):
    """No neuron-derived target placement; same fixed stimuli across controls."""
    k = approximate_intrinsics(p["width"], p["height"], p["assumed_hfov_degrees"])
    count = p["sustained_ticks"] if case == "sustained" else p["pulse_ticks"]
    for tick in range(count):
        image = np.full((p["height"], p["width"], 3), 255, np.uint8)
        active = p["pulse_start_tick"] <= tick < p["pulse_end_tick_exclusive"]
        if case == "sustained":
            x = (tick*17) % (p["width"]-p["bar_width_px"])
            image[:, x:x+p["bar_width_px"]] = 0
        elif case != "zero" and active:
            if case in ("pattern", "pattern_shuffled"):
                image[:, :p["width"]//2] = 0
            else:
                image[:] = 0
        yield Frame(image, k, tick*p["tick_ms"]/1000, "SYNTHETIC_MODEL_TIME"), {}


def recorded_frames(directory, p):
    """Causal latest-frame hold at fixed model ticks; no future frame selection."""
    import cv2
    directory = Path(directory)
    meta = json.loads((directory/"capture.json").read_text())
    display = json.loads((directory/"display_log.json").read_text())
    rp = p["recorded"]
    if display.get("protocol") != rp["protocol"]:
        raise ValueError("Expected the existing calibrated screen protocol")
    with np.load(directory/"calibrated_temporal_samples.npz", allow_pickle=False) as a:
        times, phases = a["times_s"].copy(), a["phase_id"].copy()
    start_candidates = np.flatnonzero(phases == rp["start_optical_phase"])
    if not len(start_candidates) or len(times) != len(meta["frames_timing"]) or not np.all(np.diff(times) > 0):
        raise ValueError("Invalid recording timestamps/optical phase alignment")
    start = times[start_candidates[0]]
    targets = start + np.arange(round(rp["duration_s"]/rp["tick_s"]))*rp["tick_s"]
    if targets[-1] > times[-1]:
        raise ValueError("Recording does not cover the requested model interval")
    wanted = np.searchsorted(times, targets, side="right")-1
    cap = cv2.VideoCapture(str(directory/"rgb.avi"))
    current, rgb = -1, None
    try:
        for tick, (index, target) in enumerate(zip(wanted, targets)):
            while current < index:
                ok, bgr = cap.read()
                if not ok:
                    raise ValueError("Movie ended before the declared recording interval")
                current += 1
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            age = float(target-times[index])
            frame = Frame(rgb, meta["color_intrinsics"], float(times[index]), "RECORDED_RELATIVE_CAMERA_TIME")
            if age > rp["max_frame_age_s"]:
                frame = None
            yield frame, dict(source_index=int(index), source_age_s=age,
                              optical_phase=int(phases[index]), stale=frame is None)
    finally:
        cap.release()


def identity_audit(graph):
    rows = load_eye_mapping()
    expected = {int(r["bodyId"]): r["eye"] for r in rows}
    actual = {int(body): str(side) for body, typ, side in zip(graph.body_ids, graph.types, graph.sides) if typ == "L2"}
    absent = sorted(set(expected)-set(actual))
    extra = sorted(set(actual)-set(expected))
    wrong = [body for body in set(expected) & set(actual) if expected[body] != actual[body]]
    return dict(expected_l2=len(expected), actual_l2=len(actual), missing_ids=absent,
                unexpected_ids=extra, wrong_eye_ids=sorted(wrong),
                counts_by_eye=dict(Counter(actual.values())), exact_match=not (absent or extra or wrong))


def drive_control(drive, case, shuffle_seed):
    rates = {name: value.copy() for name, value in drive.rates.items()}
    if case in ("left_pulse", "right_pulse"):
        rates["L2_R" if case == "left_pulse" else "L2_L"][:] = 0
    elif case == "pattern_shuffled":
        for name, value in rates.items():
            indices = np.flatnonzero(drive.valid[name])
            order = np.random.default_rng(shuffle_seed+(0 if name.endswith("L") else 1)).permutation(len(indices))
            value[indices] = value[indices[order]]
            if not np.array_equal(np.sort(value), np.sort(drive.rates[name])):
                raise AssertionError("Shuffle changed the input-rate multiset")
    for name, value in rates.items():
        if not np.isfinite(value).all() or np.any(value[~drive.valid[name]] != 0):
            raise AssertionError("Nonfinite or unobserved external drive")
    return rates


def run_case(graph, cfg, case, p, frames):
    from flydrones.brain import Brain
    brain = Brain(graph, cfg, seed=p["seed"])
    encoder = L2Encoder(graph, cfg)
    l2_indices = {eye: graph.group("L2_"+eye) for eye in "LR"}
    non_l2 = graph.types != "L2"
    total_counts = np.zeros(graph.n, np.int64)
    state_hash, input_hash = hashlib.sha256(), hashlib.sha256()
    ticks, input_sets, valid_sets = [], {e: set() for e in "LR"}, {e: set() for e in "LR"}
    status_counts = Counter()
    source_indices, source_ages, stale_ticks = set(), [], 0
    started = time.perf_counter()
    for i, (frame, timing) in enumerate(frames):
        if "source_index" in timing:
            source_indices.add(timing["source_index"])
            source_ages.append(timing["source_age_s"])
            stale_ticks += int(timing["stale"])
        tick_start = time.perf_counter()
        drive = encoder.encode_frame(frame)
        rates = drive_control(drive, case, p["shuffle_seed"])
        encoded = time.perf_counter()
        readout = brain.tick(rates, ms=p["tick_ms"])
        completed = time.perf_counter()
        if brain.net.t_ms != (i+1)*p["tick_ms"]:
            raise AssertionError("Persistent model clock discontinuity")
        if not all(np.isfinite(x).all() for x in (brain.net.v, brain.net.g, brain.net._buf)):
            raise AssertionError("Nonfinite LIF state")
        counts = brain.last_counts
        total_counts += counts
        state_hash.update(counts.astype("<i4").tobytes())
        for eye in "LR":
            name = "L2_"+eye
            input_hash.update(rates[name].astype("<f4").tobytes())
            input_sets[eye].update(l2_indices[eye][rates[name] > 0].tolist())
            valid_sets[eye].update(l2_indices[eye][drive.valid[name]].tolist())
        status_counts.update(c["rgb_status"] for group in drive.channels.values() for c in group)
        row = dict(case=case, tick=i, model_time_ms=brain.net.t_ms,
                   input_L_hz_sum=float(rates["L2_L"].sum()), input_R_hz_sum=float(rates["L2_R"].sum()),
                   observed_L=int(drive.valid["L2_L"].sum()), observed_R=int(drive.valid["L2_R"].sum()),
                   L2_L_spikes=int(counts[l2_indices["L"]].sum()), L2_R_spikes=int(counts[l2_indices["R"]].sum()),
                   non_L2_spikes=int(counts[non_l2].sum()), all_spikes=int(counts.sum()),
                   encoding_wall_s=encoded-tick_start, brain_wall_s=completed-encoded)
        row.update({"output_"+name+"_hz": value for name, value in readout.items() if name in cfg["outputs"]})
        ticks.append(row)
        if (i+1) % 20 == 0:
            print(f"{case}: {brain.net.t_ms:g} model ms, {int(total_counts.sum()):,} simulated spikes", flush=True)
    wall = time.perf_counter()-started
    if not ticks:
        raise ValueError("No frames evaluated")
    group_totals = {name: int(total_counts[graph.group(name)].sum()) for name in cfg["outputs"]}
    # Descriptive whole-type aggregates, not preselected biological success targets.
    types, reverse = np.unique(graph.types, return_inverse=True)
    by_type = np.bincount(reverse, weights=total_counts).astype(np.int64)
    top = sorted(zip(types, by_type), key=lambda item: (-item[1], item[0]))[:20]
    result = dict(case=case, model_ms=brain.net.t_ms, ticks=len(ticks),
                  total_simulated_spikes=int(total_counts.sum()), active_neurons=int(np.count_nonzero(total_counts)),
                  L2_spikes_by_eye={eye: int(total_counts[idx].sum()) for eye, idx in l2_indices.items()},
                  non_L2_spikes=int(total_counts[non_l2].sum()), active_non_L2_neurons=int(np.count_nonzero(total_counts[non_l2])),
                  ever_driven_ids_by_eye={eye: len(ids) for eye, ids in input_sets.items()},
                  ever_observed_ids_by_eye={eye: len(ids) for eye, ids in valid_sets.items()},
                  statuses_over_all_ticks=dict(status_counts), descending_output_group_spikes=group_totals,
                  input_rate_sha256=input_hash.hexdigest(), per_neuron_tick_count_sha256=state_hash.hexdigest(),
                  final_voltage_sha256=array_hash(brain.net.v), final_conductance_sha256=array_hash(brain.net.g),
                  wall_s=wall, brain_wall_s=sum(t["brain_wall_s"] for t in ticks),
                  encoding_wall_s=sum(t["encoding_wall_s"] for t in ticks),
                  model_seconds_per_wall_second=brain.net.t_ms/1000/wall,
                  finite_state_all_ticks=True, graph_neurons=graph.n, graph_edges=graph.n_connections)
    result["top_cell_types_by_simulated_spikes"] = [{"type": str(typ), "spikes": int(value)} for typ, value in top if value > 0]
    if source_ages:
        result["recorded_frame_selection"] = dict(distinct_frames=len(source_indices), stale_ticks=stale_ticks,
                                                 min_age_s=min(source_ages), max_age_s=max(source_ages),
                                                 first_source_index=min(source_indices), last_source_index=max(source_indices))
    del encoder, brain
    gc.collect()
    return result, ticks, total_counts


def qualify(brain_path, output, recorded_run=None):
    import flydrones
    from flydrones.brain.connectome import Connectome
    from flydrones.config import default_config
    from scipy.sparse import csc_matrix
    from .benchmark_adapters import verified_revision
    revision = verified_revision("flydrones", flydrones.__file__)
    p = json.loads(PROTOCOL.read_text())
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a new result directory")
    brain_path = Path(brain_path)
    provenance = json.loads(brain_path.with_suffix(".provenance.json").read_text())
    pinned = json.loads(Path(__file__).with_name("flydrones_network_sources.json").read_text())
    if sha(brain_path) != provenance["graph"]["sha256"] or provenance["upstream_revision"] != revision:
        raise ValueError("Graph file differs from its builder provenance")
    if provenance["sources"] != pinned["sources"] or provenance["native_meta"].get("min_synapses") != 3:
        raise ValueError("This protocol requires the pinned official tables and native minimum of 3 synapses")
    with MemoryMonitor() as memory:
        graph = Connectome.load(brain_path)
        if graph.n != provenance["neurons"] or graph.n_connections != provenance["directed_connections"]:
            raise ValueError("Graph dimensions differ from builder provenance")
        audit = identity_audit(graph)
        if not audit["exact_match"]:
            raise ValueError("Full L2 inventory/side mismatch; apply the documented official annotation fallback")
        original_weights = weight_hash(graph)
        integrity = provenance.get("compatibility_integrity", {})
        actual_content = dict(weights=original_weights, body_ids=array_hash(graph.body_ids), types=array_hash(graph.types))
        if integrity.get("before") != actual_content or integrity.get("after") != actual_content:
            raise ValueError("Graph weights/identities differ from the recorded native builder output")
        cfg = l2_config(default_config(), gain_hz=p["gain_hz"], polarity=p["polarity"])
        cfg["brain"].update(seed=p["seed"], bias=p["bias"], record_neurons=p["record_neurons"])
        cfg["brain"]["lif"].update(dt=p["dt_ms"], noise_mv=p["noise_mv"])
        results, all_ticks, counts = {}, [], {}
        for case in p["cases"]:
            con = graph
            if case == "disconnected":
                con = Connectome("Disconnected full-inventory control", csc_matrix(graph.weights.shape, dtype=np.float32),
                                 graph.types.copy(), graph.sides.copy(), body_ids=graph.body_ids.copy())
            result, ticks, totals = run_case(con, cfg, case, p, synthetic_frames(case, p))
            results[case], counts[case] = result, totals
            all_ticks.extend(ticks)
        recorded = None
        if recorded_run:
            result, ticks, totals = run_case(graph, cfg, "recorded_d435", p, recorded_frames(recorded_run, p))
            results["recorded_d435"], counts["recorded_d435"] = result, totals
            all_ticks.extend(ticks)
            recorded = dict(source_sha256={name: sha(Path(recorded_run)/name) for name in ["rgb.avi", "capture.json", "display_log.json", "calibrated_temporal_samples.npz"]},
                            selection=p["recorded"], scope="Existing private D435 recording, no new physical capture")
        unchanged = original_weights == weight_hash(graph)
        checks = dict(exact_l2_identity=audit["exact_match"], weights_unchanged=unchanged,
                      zero_input_silent=results["zero"]["total_simulated_spikes"] == 0,
                      both_eyes_active=all(v > 0 for v in results["both_pulse"]["L2_spikes_by_eye"].values()),
                      connected_propagation=results["both_pulse"]["non_L2_spikes"] > 0,
                      disconnected_no_non_L2_spikes=results["disconnected"]["non_L2_spikes"] == 0,
                      repeat_identical=all(results["both_pulse"][key] == results["both_pulse_repeat"][key] for key in
                                           ["input_rate_sha256", "per_neuron_tick_count_sha256", "final_voltage_sha256", "final_conductance_sha256"]),
                      shuffle_distinguishable=results["pattern"]["per_neuron_tick_count_sha256"] != results["pattern_shuffled"]["per_neuron_tick_count_sha256"],
                      finite_persistent_runs=all(r["finite_state_all_ticks"] for r in results.values()))
        differences = {}
        for left, right in [("both_pulse", "zero"), ("both_pulse", "disconnected"), ("pattern", "pattern_shuffled"), ("left_pulse", "right_pulse")]:
            d = counts[left]-counts[right]
            differences[left+"__vs__"+right] = dict(neurons_with_different_total_counts=int(np.count_nonzero(d)),
                                                   non_L2_neurons_with_different_total_counts=int(np.count_nonzero(d[graph.types != "L2"])),
                                                   absolute_spike_count_difference_sum=int(np.abs(d).sum()))
        report = dict(status="PASS_ENGINEERING_CHECKS" if all(checks.values()) else "CHECKS_NOT_MET", checks=checks,
                      protocol=p, protocol_sha256=sha(PROTOCOL), graph_provenance=provenance,
                      weight_array_hashes=original_weights, identity_audit=audit, configuration=cfg,
                      cases=results, differences=differences, recorded=recorded,
                      environment=dict(python=platform.python_version(), platform=platform.system(), machine=platform.machine(),
                                       versions={name: importlib.metadata.version(name) for name in ["numpy", "scipy", "flydrones", "psutil"]}),
                      limitation="Full filtered model execution and engineering controls, not biological neural-response validation or drone control")
    report["memory"] = dict(start_rss_bytes=memory.start, peak_sampled_rss_bytes=memory.peak, sampling_interval_s=.02,
                            scope="This process including native graph load, initialization and all cases; not a hard peak bound")
    output.mkdir(parents=True)
    (output/"summary.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf8")
    with (output/"ticks.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_ticks[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_ticks)
    # Per-neuron arrays remain local. Public report publishes only aggregates/hashes.
    np.savez_compressed(output/"per_neuron_totals.npz", **counts)
    print(json.dumps(dict(status=report["status"], checks=checks, memory=report["memory"]), indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recorded-run", type=Path)
    args = parser.parse_args()
    result = qualify(args.brain, args.output, args.recorded_run)
    if result["status"] != "PASS_ENGINEERING_CHECKS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
