"""Replay a saved rectified RGB frame into a native FlyDrones brain, no drone.

The same L2Encoder accepts a sequence of Frame objects from webcam/D435 readers.
This command deliberately holds one image for a bounded MODEL duration.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .bridge import Frame
from .flydrones_bridge import L2Encoder, l2_config
from .flydrones_comparison import sha
from camera_lab.biomapping.geometry import ASSUMED_HEAD_FROM_CAMERA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain", type=Path, required=True, help="Native MaleCNS FlyDrones .npz, with body_ids")
    parser.add_argument("--image", type=Path, required=True, help="Rectified RGB image")
    parser.add_argument("--intrinsics", type=Path, required=True, help="JSON fx,fy,ppx,ppy,width,height, zero coeffs")
    parser.add_argument("--head-from-camera", type=Path, help="JSON 3x3 proper rotation; default is assumed bench orientation")
    parser.add_argument("--config", type=Path, help="Optional FlyDrones YAML dynamics/output config; inputs replaced by L2")
    parser.add_argument("--eyes", choices=["left", "right", "both"], default="both")
    parser.add_argument("--polarity", choices=["brightness", "darkness"], default="darkness")
    parser.add_argument("--gain-hz", type=float, default=120)
    parser.add_argument("--model-ms", type=float, default=1000)
    parser.add_argument("--frame-ms", type=float, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new output directory")
    from flydrones.config import default_config
    from flydrones.brain import Brain
    from flydrones.brain.connectome import Connectome
    import flydrones
    from .benchmark_adapters import verified_revision
    revision = verified_revision("flydrones", flydrones.__file__)
    cfg = default_config()
    if args.config:
        import yaml
        cfg = yaml.safe_load(args.config.read_text(encoding="utf8"))
    cfg = l2_config(cfg, eyes=args.eyes, gain_hz=args.gain_hz, polarity=args.polarity)
    dt = cfg.get("brain", {}).get("lif", {}).get("dt", .5)
    if (not np.isfinite([args.model_ms, args.frame_ms, dt]).all() or min(args.model_ms, args.frame_ms, dt) <= 0 or
            not np.isclose(args.frame_ms/dt, round(args.frame_ms/dt)) or
            not np.isclose(args.model_ms/args.frame_ms, round(args.model_ms/args.frame_ms))):
        raise ValueError("frame-ms must be a positive multiple of LIF dt; model-ms a positive multiple of frame-ms")
    k = json.loads(args.intrinsics.read_text())
    rotation = json.loads(args.head_from_camera.read_text()) if args.head_from_camera else ASSUMED_HEAD_FROM_CAMERA
    rgb = np.array(Image.open(args.image).convert("RGB"))
    frame = Frame(rgb, k, 0, "SAVED_IMAGE_MODEL_TIME")
    frame.validate()
    con = Connectome.load(args.brain)
    brain = Brain(con, cfg)
    encoder = L2Encoder(con, cfg, head_from_camera=rotation)
    trace = []
    for i in range(round(args.model_ms/args.frame_ms)):
        frame.timestamp_s = i*args.frame_ms/1000
        drive = encoder.encode_frame(frame)
        outputs = brain.tick(drive.rates, ms=args.frame_ms)
        trace.append(dict(model_time_ms=brain.net.t_ms, simulated_group_rates_hz=outputs,
                          total_simulated_spikes=int(brain.last_counts.sum())))
    report = dict(upstream_revision=revision, model_sha256=sha(args.brain), image_sha256=sha(args.image),
                  config=cfg, intrinsics=k, head_from_camera=np.asarray(rotation).tolist(),
                  neurons=con.n, edges=con.n_connections,
                  scope="Static-image engineering L2 drive into native FlyDrones; no actuation or measured biological responses",
                  statuses=dict(Counter(c["rgb_status"] for group in drive.channels.values() for c in group)),
                  model_ms=brain.net.t_ms, trace=trace)
    args.output.mkdir(parents=True)
    (args.output/"summary.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf8")
    (args.output/"last_input.json").write_text(json.dumps(dict(
        channels=drive.channels, rates_hz={k: v.tolist() for k, v in drive.rates.items()},
        valid={k: v.tolist() for k, v in drive.valid.items()}), indent=2, allow_nan=False)+"\n", encoding="utf8")
    print(f"Ran {brain.net.t_ms:g} model ms; {sum(v.sum() for v in drive.valid.values())} observed L2 inputs.")


if __name__ == "__main__":
    main()
