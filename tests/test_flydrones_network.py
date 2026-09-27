"""Full-network tooling regression tests; CI never downloads the large graph."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from flyvisionbridge.flydrones_data import annotation_side_fallback, digest_file, fetch_file
from flyvisionbridge.flydrones_bridge import L2Drive
from flyvisionbridge.flydrones_network import array_hash, drive_control, recorded_frames, PROTOCOL


class AnnotationSideTests(unittest.TestCase):
    def fixture(self):
        graph = SimpleNamespace(body_ids=np.array([30, 10, 20, 40]), types=np.array(["L2", "L2", "DNp01", "X"]),
                                sides=np.array(["", "", "L", "M"]), meta={}, groups={"stale": np.array([1])},
                                weights=object())
        records = [dict(bodyId=10, type="L2", rootSide=None, somaSide="L"),
                   dict(bodyId=20, type="DNp01", rootSide="L", somaSide="R"),
                   dict(bodyId=30, type="L2", rootSide=None, somaSide="R"),
                   dict(bodyId=40, type="X", rootSide="unknown", somaSide="M")]
        return graph, records

    def test_per_row_official_fallback_preserves_ids_types_weights(self):
        graph, records = self.fixture()
        weights, ids, types = graph.weights, graph.body_ids.copy(), graph.types.copy()
        result = annotation_side_fallback(graph, records[::-1])
        self.assertEqual(graph.sides.tolist(), ["R", "L", "L", ""])
        self.assertEqual(result["l2_after"], {"R": 1, "L": 1})
        self.assertEqual(result["origins"], {"somaSide_fallback": 2, "rootSide": 1, "UNASSIGNED": 1})
        self.assertIs(weights, graph.weights)
        np.testing.assert_array_equal(ids, graph.body_ids)
        np.testing.assert_array_equal(types, graph.types)
        self.assertEqual(graph.groups, {})

    def test_ambiguous_absent_or_wrong_type_rows_fail_before_mutation(self):
        for change in [lambda rows: rows.append(rows[0]), lambda rows: rows.pop(),
                       lambda rows: rows[0].update(type="T4")]:
            graph, rows = self.fixture()
            old_sides, old_groups = graph.sides.copy(), deepcopy(graph.groups)
            change(rows)
            with self.assertRaises(ValueError):
                annotation_side_fallback(graph, rows)
            np.testing.assert_array_equal(graph.sides, old_sides)
            np.testing.assert_array_equal(graph.groups["stale"], old_groups["stale"])


class SourceDownloadTests(unittest.TestCase):
    url = "https://storage.googleapis.com/test-bucket/object.feather"

    def test_pinned_integrity_and_cached_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"object.feather"
            payload = b"a harmless synthetic fixture"
            tmp = Path(directory)/"expected"
            tmp.write_bytes(payload)
            expected = dict(url=self.url, generation="123", **digest_file(tmp))
            meta = dict(size=str(expected["bytes"]), md5Hash=expected["md5_base64"], generation="123")
            with patch("urllib.request.urlopen", side_effect=[io.BytesIO(json.dumps(meta).encode()), io.BytesIO(payload)]) as call:
                self.assertEqual(fetch_file(self.url, path, expected), expected)
                self.assertIn("generation=123", call.call_args_list[0].args[0])
                self.assertIn("generation=123", call.call_args_list[1].args[0])
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(meta).encode())) as call:
                self.assertEqual(fetch_file(self.url, path, expected), expected)
                self.assertEqual(call.call_count, 1)  # no repeated payload download
            path.write_bytes(b"corrupt")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(meta).encode())):
                with self.assertRaises(ValueError):
                    fetch_file(self.url, path, expected)

    def test_corrupt_download_retains_partial_without_creating_cache(self):
        meta = dict(size="4", md5Hash="wrongHash", generation="123")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"object.feather"
            with patch("urllib.request.urlopen", side_effect=[io.BytesIO(json.dumps(meta).encode()), io.BytesIO(b"data")]):
                with self.assertRaises(ValueError):
                    fetch_file(self.url, path)
            self.assertFalse(path.exists())
            self.assertTrue(path.with_suffix(".feather.partial").exists())


class NetworkControlTests(unittest.TestCase):
    def test_label_hash_is_content_not_python_object_addresses(self):
        labels = np.array(["L2", "Tm1"], object)
        self.assertEqual(array_hash(labels), array_hash(labels.astype(str)))
        self.assertNotEqual(array_hash(labels), array_hash(np.array(["L2", "Tm2"], object)))

    def test_shuffle_preserves_each_eye_unknowns_and_original_drive(self):
        rates = {"L2_L": np.array([0, 10, 20, 30, 0], np.float32), "L2_R": np.array([40, 30, 20, 0, 0], np.float32)}
        valid = {"L2_L": np.array([True, True, True, True, False]), "L2_R": np.array([True, True, True, False, False])}
        drive = L2Drive(rates, valid, {}, 0, "TEST")
        saved = deepcopy(rates)
        shuffled = drive_control(drive, "pattern_shuffled", 317)
        for name in rates:
            np.testing.assert_array_equal(np.sort(shuffled[name]), np.sort(saved[name]))
            np.testing.assert_array_equal(rates[name], saved[name])
            self.assertTrue(np.all(shuffled[name][~valid[name]] == 0))
        left = drive_control(drive, "left_pulse", 317)
        self.assertEqual(left["L2_R"].sum(), 0)
        np.testing.assert_array_equal(left["L2_L"], rates["L2_L"])

    @unittest.skipUnless(importlib.util.find_spec("cv2"), "OpenCV required for replay")
    def test_recorded_hold_never_selects_a_future_frame_and_drops_stale(self):
        import cv2
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            times = np.array([0, .049, .102, .15, .26, .27, .49])
            (root/"capture.json").write_text(json.dumps(dict(frames_timing=[{}]*len(times), color_intrinsics={})))
            (root/"display_log.json").write_text(json.dumps(dict(protocol="calibrated_temporal_v1")))
            np.savez(root/"calibrated_temporal_samples.npz", times_s=times, phase_id=np.full(len(times), 27))
            p = json.loads(PROTOCOL.read_text())
            p["recorded"].update(duration_s=.3, max_frame_age_s=.06)
            images = iter([np.full((2, 2, 3), i, np.uint8) for i in range(len(times))])
            cap = SimpleNamespace(read=lambda: (True, next(images)), release=lambda: None)
            with patch.object(cv2, "VideoCapture", return_value=cap):
                frames = list(recorded_frames(root, p))
            self.assertEqual([info["source_index"] for _, info in frames], [0, 1, 1, 3, 3, 3])
            self.assertIsNone(frames[-1][0])
            self.assertTrue(frames[-1][1]["stale"])
            self.assertTrue(all(info["source_age_s"] >= 0 for _, info in frames))


@unittest.skipUnless(importlib.util.find_spec("flydrones") and importlib.util.find_spec("pyarrow"), "Full-network extra required")
class NativeBuilderTests(unittest.TestCase):
    def test_native_missing_side_regression_and_exact_weight_preservation(self):
        import pyarrow as pa
        import pyarrow.feather as feather
        from flydrones.brain.connectome import build_malecns, MALECNS_FILES, GroupSpec
        from flyvisionbridge.flydrones_network import weight_hash
        from flyvisionbridge.flydrones_bridge import l2_config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [dict(bodyId=1, type="L2", superclass="ol_intrinsic", rootSide=None, somaSide="L"),
                    dict(bodyId=2, type="L2", superclass="ol_intrinsic", rootSide=None, somaSide="R"),
                    dict(bodyId=3, type="Tm1", superclass="ol_intrinsic", rootSide="L", somaSide="L")]
            feather.write_feather(pa.Table.from_pylist(rows), root/MALECNS_FILES["annotations"])
            feather.write_feather(pa.table(dict(body=[1, 2, 3], consensus_nt=["acetylcholine", "gaba", "acetylcholine"])), root/MALECNS_FILES["neurotransmitters"])
            feather.write_feather(pa.table(dict(body_pre=[1, 2, 1, 3], body_post=[3, 3, 2, 1], weight=[10, 20, 2, 7])), root/MALECNS_FILES["weights"])
            c = build_malecns(root, min_synapses=3, verbose=False)
            cfg = l2_config({})
            specs = {key: GroupSpec.from_dict(key, value) for key, value in cfg["inputs"].items()}
            c.resolve_groups(specs)
            self.assertEqual(sum(len(c.group(name)) for name in specs), 0)
            before = weight_hash(c)
            annotation_side_fallback(c, rows)
            c.resolve_groups(specs)
            self.assertEqual(c.body_ids[c.group("L2_L")].tolist(), [1])
            self.assertEqual(c.body_ids[c.group("L2_R")].tolist(), [2])
            self.assertEqual(before, weight_hash(c))
            self.assertEqual(c.n_connections, 3)
            self.assertEqual(c.weights[2, 1], -20)


if __name__ == "__main__":
    unittest.main()
