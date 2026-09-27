"""Published L2 body-ID mapping for the pinned, optional FlyDrones runtime.

This replaces the Retina/InputEncoder pair, not the LIF equations. Rates are
engineering stimuli. Missing samples have a validity sidecar and zero transport
rate; zero does NOT mean that an unobserved neuron was measured to be silent.
"""
from copy import deepcopy
from dataclasses import dataclass
import time

import numpy as np

from .bridge import Frame, load_eye_mapping, map_frame
from camera_lab.biomapping.geometry import ASSUMED_HEAD_FROM_CAMERA, rotation_checked


def l2_config(cfg, *, eyes="both", gain_hz=120.0, polarity="darkness"):
    """Copy a FlyDrones config, replacing ALL visual/IMU inputs with explicit L2.

    Construct Brain with this config BEFORE constructing L2Encoder. Outputs,
    bias and dynamics are retained, so review those separately for an experiment.
    """
    if eyes not in ("left", "right", "both"):
        raise ValueError("eyes must be left, right or both")
    if polarity not in ("brightness", "darkness"):
        raise ValueError("polarity must be brightness or darkness")
    if not np.isfinite(gain_hz) or not 0 <= gain_hz <= np.finfo(np.float32).max:
        raise ValueError("gain_hz must be finite, nonnegative and representable as float32")
    selected = {"left": "L", "right": "R", "both": "LR"}[eyes]
    out = deepcopy(cfg)
    out["inputs"] = {
        "L2_" + eye: dict(types=["^L2$"], side=eye, eye=eye,
                          feature="brightness", max_hz=float(gain_hz))
        for eye in selected
    }
    if set(out["inputs"]) & set(out.get("outputs", {})):
        raise ValueError("L2 input names must not overlap output names")
    out["column_bridge"] = dict(schema=1, eyes=eyes, polarity=polarity)
    return out


@dataclass
class L2Drive:
    """rates can go directly to Brain.tick; channels/valid must accompany logs."""
    rates: dict
    valid: dict
    channels: dict
    timestamp_s: float | None
    clock_domain: str


class L2Encoder:
    """Join published directions to actual group indices by body ID and eye.

    Connectome must carry real MaleCNS body_ids. MiniFly's invented IDs cannot
    provide that join. Unmapped IDs are supported explicitly as UNKNOWN_BODY_ID.
    Group reordering after construction raises instead of silently misrouting.
    """
    def __init__(self, connectome, cfg, *, mapping=None,
                 head_from_camera=ASSUMED_HEAD_FROM_CAMERA):
        bridge = cfg.get("column_bridge", {})
        if bridge.get("schema") != 1:
            raise ValueError("Build Brain with l2_config first")
        expected = l2_config(cfg, eyes=bridge.get("eyes"),
                             polarity=bridge.get("polarity"))
        if set(cfg.get("inputs", {})) != set(expected["inputs"]):
            raise ValueError("L2 mode cannot silently retain other input groups")
        self.specs = deepcopy(cfg["inputs"])
        self.polarity = bridge["polarity"]
        self.c = connectome
        self.rotation = rotation_checked(head_from_camera).copy()
        raw_ids = getattr(connectome, "body_ids", None)
        if raw_ids is None:
            raise ValueError("Real MaleCNS body_ids required; MiniFly has no biological ID join")
        self.raw_ids = np.asarray(raw_ids).copy()
        self.ids = np.asarray(raw_ids).astype(str)
        if self.ids.shape != (connectome.n,) or len(set(self.ids)) != len(self.ids):
            raise ValueError("Connectome body_ids must be unique, one per neuron")
        self.types = np.asarray(connectome.types).astype(str).copy()
        self.sides = np.asarray(connectome.sides).astype(str).copy()
        if self.types.shape != self.ids.shape or self.sides.shape != self.ids.shape:
            raise ValueError("Connectome type/side metadata shape mismatch")
        rows = deepcopy(load_eye_mapping(bridge["eyes"]) if mapping is None else mapping)
        if any(not isinstance(r["bodyId"], str) or r.get("eye") not in ("L", "R") for r in rows):
            raise ValueError("Mapping needs string bodyId and explicit eye")
        by_id = {r["bodyId"]: r for r in rows}
        if len(by_id) != len(rows):
            raise ValueError("Duplicate body IDs in mapping")
        self.indices = {}
        needed = set()
        for name, spec in self.specs.items():
            eye = expected["inputs"][name]["eye"]
            if (spec.get("eye") != eye or spec.get("side") != eye or
                    spec.get("types") != ["^L2$"] or spec.get("feature") != "brightness"):
                raise ValueError("L2 input spec does not match the declared eye/type")
            gain = spec.get("max_hz")
            if gain is None or not np.isfinite(gain) or not 0 <= gain <= np.finfo(np.float32).max:
                raise ValueError("Each group needs a finite nonnegative max_hz")
            idx = np.asarray(connectome.group(name))
            if idx.dtype.kind not in "iu" or idx.ndim != 1 or len(set(idx)) != len(idx):
                raise ValueError("Group indices must be unique integers")
            if np.any(idx < 0) or np.any(idx >= connectome.n):
                raise ValueError("Group index outside connectome")
            if np.any(self.types[idx] != "L2") or np.any(self.sides[idx] != eye):
                raise ValueError("Group has a wrong type or eye")
            self.indices[name] = idx.copy()
            for body_id in self.ids[idx]:
                if body_id in by_id:
                    if by_id[body_id]["eye"] != eye:
                        raise ValueError("Body ID disagrees with published eye")
                    needed.add(body_id)
        if not any(len(idx) for idx in self.indices.values()):
            raise ValueError("No L2 neurons in selected groups; construct Brain with l2_config first")
        if not needed:
            raise ValueError("No published MaleCNS L2 body IDs in selected groups")
        self.mapping = [r for r in rows if r["bodyId"] in needed]
        self.last_drive = None

    def _check_identity(self):
        # Protect callers who mutate groups or replace a graph after installation.
        if (not np.array_equal(self.raw_ids, np.asarray(self.c.body_ids)) or
                not np.array_equal(self.types, self.c.types) or
                not np.array_equal(self.sides, self.c.sides) or
                any(not np.array_equal(idx, self.c.group(name)) for name, idx in self.indices.items())):
            raise ValueError("Connectome identity/groups changed; rebuild the L2 encoder")

    def encode_frame(self, frame, *, valid_mask=None):
        """Frame or None -> finite input rates plus per-ID observation status.

        valid_mask is an optional Boolean HxW sensor/rectification mask. All four
        bilinear neighbours must be valid. Missing depth never invalidates RGB.
        None explicitly drops the current frame and clears all external drive.
        """
        self._check_identity()
        if frame is None:
            if valid_mask is not None:
                raise ValueError("A mask without a frame is ambiguous")
            by_id = {}
        else:
            mapped = map_frame(frame, self.mapping, self.rotation)
            if valid_mask is not None:
                mask = np.asarray(valid_mask)
                if mask.dtype != np.bool_ or mask.shape != frame.rgb.shape[:2]:
                    raise ValueError("valid_mask must be Boolean with the RGB height and width")
                for channel in mapped["channels"]:
                    if channel["rgb_status"] == "OBSERVED":
                        x, y = np.floor(channel["pixel_uv"]).astype(int)
                        if not mask[y:y+2, x:x+2].all():
                            channel["rgb_status"] = "INVALID_PIXEL_MASK"
                            channel["rgb_code_luminance"] = None
            by_id = {c["bodyId"]: c for c in mapped["channels"]}
        rates, valid, channels = {}, {}, {}
        for name, idx in self.indices.items():
            channels[name] = []
            for body_id in self.ids[idx]:
                c = by_id.get(body_id)
                if c is None:
                    c = dict(bodyId=str(body_id), eye=self.specs[name]["eye"],
                             rgb_status="NO_FRAME" if frame is None else "UNKNOWN_BODY_ID",
                             rgb_code_luminance=None, pixel_uv=None)
                channels[name].append(c)
            valid[name] = np.array([c["rgb_status"] == "OBSERVED" for c in channels[name]], bool)
            rates[name] = np.zeros(len(idx), np.float32)
            for i in np.flatnonzero(valid[name]):
                value = channels[name][i]["rgb_code_luminance"]
                if value is None or not np.isfinite(value) or not 0 <= value <= 1.000001:
                    raise ValueError("Observed luminance must be finite in [0,1]")
                value = np.clip(value, 0, 1)
                if self.polarity == "darkness":
                    value = 1 - value
                rates[name][i] = self.specs[name]["max_hz"] * value
        self.last_drive = L2Drive(rates, valid, channels,
                                 None if frame is None else frame.timestamp_s,
                                 "NO_FRAME" if frame is None else frame.clock_domain)
        return self.last_drive

    def encode(self, vision, yaw_rate_dps=0.0, extra=None):
        """FlyDrones InputEncoder signature; pair with CameraRetina below.

        L2-only mode does not inject yaw/IMU. Gesture feature overrides are not
        spatial observations and are rejected instead of fabricating pixels.
        """
        if extra:
            raise ValueError("Gesture/feature overrides are unsupported in published L2 mode")
        return self.encode_frame(vision).rates


class CameraRetina:
    """Keep raw rectified RGB for L2Encoder; no split into image-half eyes."""
    def __init__(self, intrinsics):
        self.intrinsics = deepcopy(intrinsics)

    def encode(self, rgb):
        if rgb is None:
            return None
        frame = Frame(rgb, self.intrinsics, time.monotonic(), "HOST_MONOTONIC")
        frame.validate()
        return frame

    def reset(self):
        pass  # The geometric sampler has no temporal state.


def install_l2_bridge(pilot, intrinsics, *, head_from_camera=ASSUMED_HEAD_FROM_CAMERA):
    """Replace a configured Pilot's Retina/encoder pair, without running it.

    The neural image comes from pilot.drone.frame(), NOT Pilot.webcam (which
    upstream uses for gestures/display). Only the camera/brain software path is
    qualified here; installing this is not a flight-controller validation.
    """
    if pilot.gestures is not None or pilot.webcam is not None:
        raise ValueError("Use drone.frame() for neural RGB; gestures/webcam overlay are unsupported")
    if pilot.cfg.get("inputs") != pilot.brain.cfg.get("inputs") or pilot.cfg.get("column_bridge") != pilot.brain.cfg.get("column_bridge"):
        raise ValueError("Pilot and Brain must use the same l2_config")
    encoder = L2Encoder(pilot.brain.connectome, pilot.cfg, head_from_camera=head_from_camera)
    retina = CameraRetina(intrinsics)
    pilot.retina, pilot.encoder = retina, encoder
    return encoder
