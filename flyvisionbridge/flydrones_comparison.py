"""Reproducible, matched-L2 comparison with the pinned upstream index-grid map.

Run: python -m flyvisionbridge.flydrones_comparison --output outputs/l2-adapter
Optional --recorded-run consumes private D435 screen recordings; only aggregate
metrics and content hashes are written. Original benchmark_protocol is untouched.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from .bridge import Frame, RESOLVED, load_eye_mapping
from .flydrones_bridge import L2Encoder, l2_config
from .live_core import approximate_intrinsics

PROTOCOL = Path(__file__).with_name("flydrones_protocol.json")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def population(rows, cfg):
    """Real identities, explicitly EMPTY synthetic wiring; no fabricated connectome."""
    from scipy.sparse import csc_matrix
    from flydrones.brain.connectome import Connectome, GroupSpec
    c = Connectome("L2 mapping fixture; EMPTY synthetic wiring",
                  csc_matrix((len(rows), len(rows))), np.array(["L2"]*len(rows)),
                  np.array([r["eye"] for r in rows]),
                  body_ids=np.array([int(r["bodyId"]) for r in rows], np.int64))
    c.resolve_groups({name: GroupSpec.from_dict(name, spec) for name, spec in cfg["inputs"].items()})
    return c


def flat_rates(c, rates):
    return {str(c.body_ids[i]): float(value)
            for name, values in rates.items() for i, value in zip(c.group(name), values)}


def vector(values, ids):
    return np.array([values[i] for i in ids], float)


def angle_positions(rows, k):
    """Independent of project_rays/ray_head_xyz; assumed head/camera rotation only."""
    uv = np.full((len(rows), 2), np.nan)
    visible = np.zeros(len(rows), bool)
    for i, r in enumerate(rows):
        if r["status"] != RESOLVED:
            continue
        a, e = np.deg2rad([r["azimuth_left_deg"], r["elevation_deg"]])
        forward = np.cos(e)*np.cos(a)
        if forward <= 1e-8:
            continue
        uv[i] = [k["ppx"]-k["fx"]*np.tan(a), k["ppy"]-k["fy"]*np.tan(e)/np.cos(a)]
        u, v = uv[i]
        visible[i] = 0 <= u < k["width"]-1 and 0 <= v < k["height"]-1
    return uv, visible


def stats(values):
    a = np.asarray(values)
    a = a[np.isfinite(a)]
    return dict(n=int(a.size), median=float(np.median(a)) if a.size else None,
                p95=float(np.percentile(a, 95)) if a.size else None,
                maximum=float(a.max()) if a.size else None)


def ramp_frames(p):
    w, h = p["width"], p["height"]
    for axis, size in [(0, w), (1, h)]:
        codes = np.rint(np.linspace(p["ramp_low"], p["ramp_high"], size)).astype(np.uint8)
        plane = np.broadcast_to(codes[None, :] if axis == 0 else codes[:, None], (h, w))
        yield np.repeat(plane[..., None], 3, axis=2)


def compare(p):
    import flydrones
    from flydrones.config import default_config
    from flydrones.senses.encoder import InputEncoder
    from flydrones.senses.retina import Retina
    from .benchmark_adapters import verified_revision
    revision = verified_revision("flydrones", flydrones.__file__)
    rows = sorted(load_eye_mapping(), key=lambda r: int(r["bodyId"]))
    ids = [r["bodyId"] for r in rows]
    cfg = l2_config(default_config(), gain_hz=p["gain_hz"], polarity=p["polarity"])
    cfg["brain"]["bias"] = {}
    c = population(rows, cfg)
    k = approximate_intrinsics(p["width"], p["height"], p["assumed_hfov_degrees"])
    rgb = list(ramp_frames(p))

    def evaluate(con):
        native, retina, adapter = InputEncoder(con, cfg), Retina.from_config(cfg), L2Encoder(con, cfg)
        out = {"upstream_index_grid": [], "published_column_bridge": []}
        for t, image in enumerate(rgb):
            retina.reset()
            out["upstream_index_grid"].append(vector(flat_rates(con, native.encode(retina.encode(image))), ids))
            drive = adapter.encode_frame(Frame(image, k, t, "SYNTHETIC"))
            out["published_column_bridge"].append(vector(flat_rates(con, drive.rates), ids))
        return {name: np.array(values) for name, values in out.items()}, adapter

    rates, adapter = evaluate(c)
    uv, visible = angle_positions(rows, k)
    observed_ids = {ch["bodyId"] for channels in adapter.last_drive.channels.values() for ch in channels if ch["rgb_status"] == "OBSERVED"}
    if observed_ids != {ids[i] for i in np.flatnonzero(visible)}:
        raise AssertionError("Independent visibility disagrees with the adapter")
    summary = {}
    for name, rr in rates.items():
        inferred = ((rr.T/p["gain_hz"]*255-p["ramp_low"])/(p["ramp_high"]-p["ramp_low"])) * [p["width"]-1, p["height"]-1]
        errors = np.linalg.norm(inferred[visible]-uv[visible], axis=1)
        summary[name] = dict(position_error_camera_px=stats(errors),
                             within_2px=int((errors <= p["position_tolerance_camera_px"]).sum()),
                             scored_visible_ids=int(visible.sum()))
    # Same-ID scores, even when the physical storage/group order changes.
    permutations = []
    for seed in p["permutation_seeds"]:
        order = np.random.default_rng(seed).permutation(len(rows))
        changed, _ = evaluate(population([rows[i] for i in order], cfg))
        permutations.append(dict(seed=seed, **{name: dict(
            max_rate_difference_hz=float(np.abs(changed[name]-rates[name]).max()),
            changed_ids=int(np.any(np.abs(changed[name]-rates[name]) > 1e-5, axis=0).sum())) for name in rates}))
    repeats = []
    for _ in range(p["repeat_count"]):
        rr, _ = evaluate(c)
        repeats.append({name: float(np.abs(rr[name]-rates[name]).max()) for name in rates})
    uniform = {}
    for code in p["uniform_codes"]:
        image = np.full((p["height"], p["width"], 3), code, np.uint8)
        drive = adapter.encode_frame(Frame(image, k, 0, "SYNTHETIC"))
        other = InputEncoder(c, cfg).encode(Retina.from_config(cfg).encode(image))
        uniform[str(code)] = float(np.abs(vector(flat_rates(c, drive.rates), ids)[visible] - vector(flat_rates(c, other), ids)[visible]).max())
    statuses = Counter(ch["rgb_status"] for group in adapter.last_drive.channels.values() for ch in group)
    mask = np.ones((p["height"], p["width"]), bool)
    mask[:, :int(p["width"]*p["mask_x_fraction"])] = False
    masked = adapter.encode_frame(Frame(rgb[0], k, 0, "SYNTHETIC"), valid_mask=mask)
    masked_counts = Counter(ch["rgb_status"] for group in masked.channels.values() for ch in group)
    drop = adapter.encode_frame(None)
    native_drop = InputEncoder(c, cfg).encode(Retina.from_config(cfg).encode(None))
    return dict(protocol_sha256=sha(PROTOCOL), upstream_revision=revision, population=len(rows),
                eyes=dict(Counter(r["eye"] for r in rows)),
                wiring="EMPTY synthetic fixture; spatial scores do not involve brain dynamics",
                config=cfg, intrinsics=k,
                stimulus_sha256=[hashlib.sha256(x.tobytes()).hexdigest() for x in rgb],
                position=summary, permutation=permutations, repeats_max_difference_hz=repeats,
                uniform_max_difference_hz=uniform,
                missing=dict(bridge_status_counts=dict(statuses), masked_status_counts=dict(masked_counts),
                             upstream_validity_sidecar="Unavailable in native InputEncoder API",
                             bridge_dropped_frame_nonzero=int(sum(np.count_nonzero(x) for x in drop.rates.values())),
                             upstream_dropped_frame_nonzero=int(sum(np.count_nonzero(x) for x in native_drop.values())),
                             note="Both send zero on a dropped frame. Only the bridge distinguishes missing from observed black at this API.")), cfg, rows


def recorded_comparison(directory, p, cfg, rows):
    """Use frozen prior optical labels/registration, never fit the tested encoders.

    The file hashes make this local replay auditable. Private recording bytes and
    per-ID traces are not published. Synthetic comparison is fully public.
    """
    import cv2
    from flydrones.senses.encoder import InputEncoder
    from flydrones.senses.retina import Retina
    directory = Path(directory)
    meta = json.loads((directory/"capture.json").read_text())
    display = json.loads((directory/"display_log.json").read_text())
    if display.get("protocol") != "calibrated_temporal_v1" or display.get("bit_encoding") != "gray_dualrail_v2":
        raise ValueError("Recording does not match the declared optical protocol")
    if sha(directory/"frozen_response_lut.json") != meta["frozen_lut_sha256"]:
        raise ValueError("Frozen calibration identity mismatch")
    lut = json.loads((directory/"frozen_response_lut.json").read_text())
    with np.load(directory/"calibrated_temporal_samples.npz", allow_pickle=False) as a:
        target_ids = a["L2_bodyIds"].astype(str).tolist()
        times, labels, xy = a["times_s"].copy(), a["phase_id"].copy(), a["screen_xy"].copy()
    if set(target_ids) != {name[3:] for name in lut["channels"] if name.startswith("L2_")}:
        raise ValueError("Scored cell IDs differ from the pre-existing calibration cohort")
    if len(times) != len(meta["frames_timing"]) or xy.shape != (len(times), len(target_ids), 2):
        raise ValueError("Optical labels and movie metadata disagree")
    k = meta["color_intrinsics"]
    c = population(rows, cfg)
    adapter, encoder, retina = L2Encoder(c, cfg), InputEncoder(c, cfg), Retina.from_config(cfg)
    traces = {"upstream_index_grid": [], "published_column_bridge": []}
    cap = cv2.VideoCapture(str(directory/"rgb.avi"))
    try:
        for i, t in enumerate(times):
            ok, bgr = cap.read()
            if not ok:
                raise ValueError("Movie ended before optical labels")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            drive = adapter.encode_frame(Frame(rgb, k, float(t), "RECORDED_RELATIVE_CAMERA_TIME"))
            traces["published_column_bridge"].append(vector(flat_rates(c, drive.rates), target_ids)*255/p["gain_hz"])
            traces["upstream_index_grid"].append(vector(flat_rates(c, encoder.encode(retina.encode(rgb))), target_ids)*255/p["gain_hz"])
        if cap.read()[0]:
            raise ValueError("Movie has more frames than optical labels")
    finally:
        cap.release()
    rp = p["recorded"]
    results, passage_data = {}, {}
    for name, values in traces.items():
        values = np.array(values)
        conditions = []
        for phase, baseline_phase, direction in zip(rp["phase_ids"], rp["baseline_phase_ids"], [1, -1]):
            use, base = labels == phase, labels == baseline_phase
            if use.sum() < rp["min_phase_frames"] or base.sum() < rp["min_baseline_frames"]:
                raise ValueError("Insufficient independently labelled screen frames")
            baseline = np.median(values[base], axis=0)
            difference = baseline-values[use]
            weights = np.maximum(difference-rp["noise_floor_camera_codes"], 0)
            amplitude = np.percentile(difference, 95, axis=0)
            detected = (amplitude >= rp["min_dark_amplitude_camera_codes"]) & (weights.sum(axis=0) > 0)
            screen_x = np.nanmedian(xy[use, :, 0], axis=0)
            detected &= np.isfinite(screen_x)
            passages = np.divide((weights*times[use, None]).sum(axis=0), weights.sum(axis=0),
                                 out=np.full(len(target_ids), np.nan), where=detected)
            passage_data[name, phase] = (detected, passages, screen_x)
            ids = np.flatnonzero(detected)
            pairs = [(a, b) for q, a in enumerate(ids) for b in ids[q+1:] if abs(screen_x[a]-screen_x[b]) > 1]
            errors = [abs((passages[a]-passages[b])-direction*(screen_x[a]-screen_x[b])/rp["screen_px_per_second"]) for a, b in pairs]
            correct = [np.sign(passages[a]-passages[b]) == direction*np.sign(screen_x[a]-screen_x[b]) for a, b in pairs]
            conditions.append(dict(phase_id=phase, phase_frames=int(use.sum()), baseline_frames=int(base.sum()),
                                   expected_ids=len(target_ids), detected_ids=int(detected.sum()),
                                   compared_pairs=len(pairs), pairwise_error_s=stats(errors),
                                   correct_passage_order_fraction=float(np.mean(correct)) if pairs else None,
                                   amplitudes_camera_code=stats(amplitude)))
        results[name] = conditions
    matched = []
    for phase, direction in zip(rp["phase_ids"], [1, -1]):
        common = np.logical_and.reduce([passage_data[name, phase][0] for name in traces])
        indices = np.flatnonzero(common)
        screen_x = passage_data[next(iter(traces)), phase][2]
        pairs = [(a, b) for q, a in enumerate(indices) for b in indices[q+1:] if abs(screen_x[a]-screen_x[b]) > 1]
        item = dict(phase_id=phase, common_detected_ids=int(common.sum()), compared_pairs=len(pairs))
        for name in traces:
            passages = passage_data[name, phase][1]
            errors = [abs((passages[a]-passages[b])-direction*(screen_x[a]-screen_x[b])/rp["screen_px_per_second"]) for a, b in pairs]
            correct = [np.sign(passages[a]-passages[b]) == direction*np.sign(screen_x[a]-screen_x[b]) for a, b in pairs]
            item[name] = dict(pairwise_error_s=stats(errors), correct_passage_order_fraction=float(np.mean(correct)) if pairs else None)
        matched.append(item)
    return dict(scope=rp["scope"], frame_count=len(times), target_ids_count=len(target_ids),
                target_eyes="R (the existing calibrated cohort only)",
                input_sha256={name: sha(directory/name) for name in ["rgb.avi", "capture.json", "display_log.json", "frozen_response_lut.json", "calibrated_temporal_samples.npz"]},
                results=results, common_detected_pair_comparison=matched,
                limitations=["Retrospective replay, not a fresh independent acquisition",
                             "Screen labels/positions from earlier fiducial analysis; published cell positions are not measured receptive fields",
                             "Native sampling footprints and RGB weights differ; raw camera-code amplitudes are not biological units",
                             "No per-ID LUT applied to either encoder, no fitted time shift, no inference from absent bar responses",
                             "Raw private capture not redistributed; this recorded result is not independently reproducible from repository bytes alone"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recorded-run", type=Path)
    args = parser.parse_args()
    if (args.output/"summary.json").exists():
        raise FileExistsError("Choose a new output directory to preserve earlier results")
    p = json.loads(PROTOCOL.read_text())
    result, cfg, rows = compare(p)
    if args.recorded_run:
        result["recorded"] = recorded_comparison(args.recorded_run, p, cfg, rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"summary.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf8")
    print(json.dumps({"position": result["position"], "missing": result["missing"],
                      "recorded": result.get("recorded", {}).get("results")}, indent=2))


if __name__ == "__main__":
    main()
