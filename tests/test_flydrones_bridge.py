"""Identity/unknown handling and an actual upstream Brain/Pilot integration."""
from copy import deepcopy
import importlib.util
from types import SimpleNamespace
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from flyvisionbridge.bridge import Frame, load_eye_mapping, map_frame
from flyvisionbridge.live_core import approximate_intrinsics
from flyvisionbridge.flydrones_bridge import L2Encoder, CameraRetina, l2_config, install_l2_bridge


def fixture():
    k = approximate_intrinsics(96, 72, 90)
    frame = Frame(np.full((72, 96, 3), 128, np.uint8), k, 1, "TEST")
    rows = load_eye_mapping()
    mapped = map_frame(frame, rows)["channels"]
    observed = [next(c["bodyId"] for c in mapped if c["rgb_status"] == "OBSERVED" and c["eye"] == eye) for eye in "LR"]
    missing = next(c["bodyId"] for c in mapped if c["rgb_status"] == "MISSING_DIRECTION" and c["eye"] == "R")
    outside = next(c["bodyId"] for c in mapped if c["rgb_status"] == "OUTSIDE_CAMERA_FOV" and c["eye"] == "R")
    ids = np.array([observed[0], observed[1], missing, outside, "999999999999"])
    groups = {"L2_L": np.array([0]), "L2_R": np.array([1, 2, 3, 4])}
    c = SimpleNamespace(n=5, body_ids=ids, types=np.array(["L2"]*5),
                        sides=np.array(list("LRRRR")), groups=groups)
    c.group = lambda name: c.groups.get(name, np.array([], int))
    cfg = l2_config({}, polarity="brightness")
    return c, cfg, frame


class L2BridgeTests(unittest.TestCase):
    def test_config_replaces_inputs_but_does_not_mutate_caller(self):
        original = {"inputs": {"T4": {"types": ["T4"]}}, "outputs": {"DN": {}}, "brain": {"bias": {"DN": 9}}}
        saved = deepcopy(original)
        cfg = l2_config(original, eyes="left")
        self.assertEqual(original, saved)
        self.assertEqual(set(cfg["inputs"]), {"L2_L"})
        self.assertEqual(cfg["outputs"], original["outputs"])
        self.assertEqual(cfg["brain"], original["brain"])

    def test_unknowns_are_not_black_pixels(self):
        c, cfg, frame = fixture()
        drive = L2Encoder(c, cfg).encode_frame(frame)
        self.assertEqual(drive.rates["L2_R"].dtype, np.float32)
        np.testing.assert_allclose(drive.rates["L2_R"], [120*128/255, 0, 0, 0])
        self.assertEqual([x["rgb_status"] for x in drive.channels["L2_R"]],
                         ["OBSERVED", "MISSING_DIRECTION", "OUTSIDE_CAMERA_FOV", "UNKNOWN_BODY_ID"])
        frame.rgb[:] = 0
        dark = L2Encoder(c, l2_config({}, polarity="darkness")).encode_frame(frame)
        self.assertEqual(dark.rates["L2_R"].tolist(), [120, 0, 0, 0])
        self.assertEqual(dark.valid["L2_R"].tolist(), [True, False, False, False])

    def test_explicit_drop_clears_prior_drive(self):
        c, cfg, frame = fixture()
        enc = L2Encoder(c, cfg)
        self.assertGreater(enc.encode_frame(frame).rates["L2_R"].sum(), 0)
        dropped = enc.encode_frame(None)
        self.assertEqual(sum(x.sum() for x in dropped.rates.values()), 0)
        self.assertTrue(all(x["rgb_status"] == "NO_FRAME" for group in dropped.channels.values() for x in group))

    def test_mask_requires_all_bilinear_neighbours(self):
        c, cfg, frame = fixture()
        enc = L2Encoder(c, cfg)
        drive = enc.encode_frame(frame)
        x, y = np.floor(drive.channels["L2_R"][0]["pixel_uv"]).astype(int)
        mask = np.ones(frame.rgb.shape[:2], bool)
        mask[y+1, x+1] = False
        masked = enc.encode_frame(frame, valid_mask=mask)
        self.assertEqual(masked.channels["L2_R"][0]["rgb_status"], "INVALID_PIXEL_MASK")
        self.assertEqual(masked.rates["L2_R"][0], 0)
        with self.assertRaises(ValueError):
            enc.encode_frame(frame, valid_mask=mask.astype(np.uint8))

    def test_group_order_is_followed_and_later_mutation_detected(self):
        c, cfg, frame = fixture()
        c.groups["L2_R"] = np.array([4, 3, 2, 1])
        enc = L2Encoder(c, cfg)
        self.assertTrue(enc.encode_frame(frame).valid["L2_R"][-1])
        self.assertEqual(enc.encode_frame(frame).channels["L2_R"][0]["bodyId"], "999999999999")
        c.groups["L2_R"] = np.array([1, 2, 3, 4])
        with self.assertRaises(ValueError):
            enc.encode_frame(frame)

    def test_wrong_identity_and_group_metadata_fail_closed(self):
        for mutation in (lambda c: setattr(c, "body_ids", None),
                         lambda c: c.body_ids.__setitem__(1, c.body_ids[0]),
                         lambda c: c.sides.__setitem__(1, "L"),
                         lambda c: c.types.__setitem__(1, "T4")):
            c, cfg, _ = fixture()
            mutation(c)
            with self.assertRaises(ValueError):
                L2Encoder(c, cfg)
        c, cfg, _ = fixture()
        c.body_ids[0], c.body_ids[1] = c.body_ids[1], c.body_ids[0]
        with self.assertRaises(ValueError):
            L2Encoder(c, cfg)

    def test_duplicate_mapping_and_mixed_config_rejected(self):
        c, cfg, _ = fixture()
        rows = load_eye_mapping()
        with self.assertRaises(ValueError):
            L2Encoder(c, cfg, mapping=rows + rows[:1])
        cfg["inputs"]["HAL_L"] = {}
        with self.assertRaises(ValueError):
            L2Encoder(c, cfg)

    def test_subgraph_by_id_matches_full_mapping(self):
        c, cfg, frame = fixture()
        enc = L2Encoder(c, cfg)
        drive = enc.encode_frame(frame)
        mapped = {ch["bodyId"]: ch for ch in map_frame(frame, load_eye_mapping())["channels"]}
        for group in drive.channels.values():
            for ch in group:
                if ch["bodyId"] in mapped:
                    self.assertEqual(ch, mapped[ch["bodyId"]])

    def test_frame_geometry_and_rotation_are_checked(self):
        c, cfg, frame = fixture()
        with self.assertRaises(ValueError):
            L2Encoder(c, cfg, head_from_camera=np.diag([-1, 1, 1]))
        frame.intrinsics["coeffs"] = [.1, 0, 0, 0, 0]
        with self.assertRaises(ValueError):
            L2Encoder(c, cfg).encode_frame(frame)
        with self.assertRaises(ValueError):
            CameraRetina(frame.intrinsics).encode(frame.rgb)


@unittest.skipUnless(importlib.util.find_spec("flydrones"), "Install the pinned flydrones extra")
class UpstreamIntegrationTests(unittest.TestCase):
    def test_static_image_cli_drives_native_saved_graph(self):
        from PIL import Image
        import yaml
        brain, cfg, frame = self.make_brain()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            brain.connectome.save(root/"brain.npz")
            Image.fromarray(frame.rgb).save(root/"rgb.png")
            (root/"intrinsics.json").write_text(json.dumps(frame.intrinsics))
            (root/"config.yaml").write_text(yaml.safe_dump(cfg))
            cmd = [sys.executable, "-m", "flyvisionbridge.flydrones_run", "--brain", str(root/"brain.npz"),
                   "--image", str(root/"rgb.png"), "--intrinsics", str(root/"intrinsics.json"),
                   "--config", str(root/"config.yaml"), "--model-ms", "100", "--frame-ms", "50",
                   "--output", str(root/"result")]
            run = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads((root/"result/summary.json").read_text())
            self.assertEqual(report["model_ms"], 100)
            self.assertEqual(report["neurons"], 5)
            self.assertEqual(report["edges"], 0)
            self.assertEqual(report["statuses"]["OBSERVED"], 2)
            self.assertGreater(sum(t["total_simulated_spikes"] for t in report["trace"]), 0)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)

    def test_frozen_spatial_comparison_is_reproducible(self):
        import json
        from flyvisionbridge.flydrones_comparison import compare, PROTOCOL
        result, _, _ = compare(json.loads(PROTOCOL.read_text()))
        self.assertEqual(result["population"], 1779)
        position = result["position"]["published_column_bridge"]
        self.assertEqual(position["within_2px"], position["scored_visible_ids"])
        for permutation in result["permutation"]:
            self.assertEqual(permutation["published_column_bridge"]["changed_ids"], 0)
        for repeat in result["repeats_max_difference_hz"]:
            self.assertTrue(all(d == 0 for d in repeat.values()))
        self.assertEqual(result["missing"]["bridge_dropped_frame_nonzero"], 0)
        self.assertEqual(result["missing"]["bridge_status_counts"]["MISSING_DIRECTION"], 85)

    def make_brain(self, seed=7):
        from scipy.sparse import csc_matrix
        from flydrones.brain import Brain
        from flydrones.brain.connectome import Connectome
        from flydrones.config import default_config
        c, _, frame = fixture()
        cfg = l2_config(default_config(), polarity="brightness")
        cfg["outputs"] = {}
        cfg["brain"]["bias"] = {}
        # Deliberately empty synthetic wiring: qualify injection, not real MaleCNS propagation.
        con = Connectome("SYNTHETIC wiring / real ID metadata", csc_matrix((c.n, c.n)),
                         c.types, c.sides, body_ids=c.body_ids.astype(np.int64))
        return Brain(con, cfg, seed=seed), cfg, frame

    def test_native_brain_tick_and_seeded_replay(self):
        outputs = []
        for _ in range(2):
            brain, cfg, frame = self.make_brain()
            enc = L2Encoder(brain.connectome, cfg)
            drive = enc.encode_frame(frame)
            brain.tick(drive.rates, ms=100)
            self.assertEqual(brain.net.t_ms, 100)
            self.assertGreater(brain.last_counts[:2].sum(), 0)
            self.assertEqual(brain.last_counts[2:].sum(), 0)
            outputs.append(brain.last_counts.copy())
            brain.tick(enc.encode_frame(None).rates, ms=100)
            brain.tick(enc.encode_frame(None).rates, ms=100)
            self.assertEqual(brain.last_counts.sum(), 0)
        np.testing.assert_array_equal(*outputs)

    def test_pilot_pair_replacement_runs_actual_tick_without_actuator(self):
        from flydrones.runtime import Pilot
        from flydrones.safety import Telemetry
        brain, cfg, frame = self.make_brain()
        sent = []
        drone = SimpleNamespace(has_camera=True, frame=lambda: frame.rgb,
                                telemetry=lambda: Telemetry(), send=sent.append,
                                land=lambda: sent.append("LAND"))
        pilot = Pilot(brain, drone, cfg)
        enc = install_l2_bridge(pilot, frame.intrinsics)
        info = pilot.tick(0, .1)
        self.assertEqual(info.brain_ms, 100)
        self.assertEqual(len(sent), 1)
        self.assertEqual(enc.last_drive.valid["L2_R"].tolist(), [True, False, False, False])
        pilot.webcam = object()
        with self.assertRaises(ValueError):
            install_l2_bridge(pilot, frame.intrinsics)


if __name__ == "__main__":
    unittest.main()
