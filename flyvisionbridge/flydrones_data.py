"""Fetch official MaleCNS v1.0 tables and invoke the pinned native builder.

No connectivity is bundled in this repository. The files remain under their
upstream CC BY 4.0 terms. GCS object generation, server MD5 and local SHA256 are
recorded so the exact inputs can be audited without redistributing the graph.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse

import numpy as np


def annotation_side_fallback(graph, records):
    """Resolve side per ROW from official annotations, never from the eye map.

    Pinned upstream picks the rootSide COLUMN even when its value is missing.
    All real L2 rows have this problem. Keep an explicit L/R rootSide; otherwise
    use an explicit L/R somaSide. Midline/unknown remains unassigned. This changes
    side metadata only, and must run before Brain resolves named groups.
    """
    by_id = {str(int(r["bodyId"])): r for r in records}
    if len(by_id) != len(records):
        raise ValueError("Duplicate official annotation body ID")
    sides, origins = [], []
    for body_id, typ in zip(graph.body_ids, graph.types):
        record = by_id.get(str(int(body_id)))
        if record is None:
            raise ValueError("Graph ID absent from official annotations")
        recorded_type = record.get("type")
        if recorded_type is None or isinstance(recorded_type, float) and np.isnan(recorded_type):
            recorded_type = ""
        if str(recorded_type) != str(typ):
            raise ValueError("Graph/annotation cell type mismatch")
        root, soma = record.get("rootSide"), record.get("somaSide")
        if root in ("L", "R"):
            sides.append(root)
            origins.append("rootSide")
        elif soma in ("L", "R"):
            sides.append(soma)
            origins.append("somaSide_fallback")
        else:
            sides.append("")
            origins.append("UNASSIGNED")
    sides = np.asarray(sides)
    if sides.shape != graph.sides.shape:
        raise ValueError("Graph identity/side shapes disagree")
    from collections import Counter
    l2 = graph.types == "L2"
    report = dict(policy="Explicit L/R rootSide per row, else explicit L/R somaSide, else unassigned",
                  changed_neurons=int(np.count_nonzero(sides != graph.sides)),
                  origins=dict(Counter(origins)),
                  l2_before=dict(Counter(graph.sides[l2].tolist())),
                  l2_after=dict(Counter(sides[l2].tolist())),
                  weight_change="NONE; only side metadata assigned by matching official body ID")
    graph.sides = sides
    graph.groups = {}  # previous derived group memberships are stale
    graph.meta["bridge_side_compatibility"] = report
    return report


def digest_file(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    size = 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            sha.update(block)
            md5.update(block)
            size += len(block)
    return dict(bytes=size, sha256=sha.hexdigest(), md5_base64=base64.b64encode(md5.digest()).decode())


def fetch_file(url, path, pinned=None):
    """Require GCS size/MD5, including for an already cached file."""
    path = Path(path)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "storage.googleapis.com":
        raise ValueError("Expected an official HTTPS GCS object URL")
    bucket, object_name = parsed.path.lstrip("/").split("/", 1)
    metadata_url = "https://storage.googleapis.com/storage/v1/b/"+bucket+"/o/"+urllib.parse.quote(object_name, safe="")
    if pinned:
        if pinned["url"] != url:
            raise ValueError("Pinned source URL differs from the upstream builder")
        metadata_url += "?generation="+pinned["generation"]
    # JSON metadata includes MD5 even when a HEAD proxy only exposes CRC32C.
    with urllib.request.urlopen(metadata_url, timeout=60) as response:
        metadata = json.load(response)
    length = int(metadata["size"])
    expected, generation = metadata.get("md5Hash"), metadata.get("generation")
    if not expected or not generation:
        raise ValueError("Server did not provide the expected immutable-object integrity metadata")
    if pinned and (generation != pinned["generation"] or length != pinned["bytes"] or expected != pinned["md5_base64"]):
        raise ValueError("Official object metadata differs from the pinned source")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix+".partial")
        # Failed partial downloads are preserved; explicitly choose a new directory
        # or remove only that known partial file before retrying.
        pinned_url = url+"?generation="+generation
        done, last = 0, time.monotonic()
        with urllib.request.urlopen(pinned_url, timeout=120) as response, partial.open("xb") as out:
            while block := response.read(8*1024*1024):
                out.write(block)
                done += len(block)
                if time.monotonic()-last >= 10:
                    print(f"{path.name}: {done/1e6:.0f}/{length/1e6:.0f} MB", flush=True)
                    last = time.monotonic()
        info = digest_file(partial)
        if info["bytes"] != length or info["md5_base64"] != expected:
            raise ValueError("Downloaded object size/MD5 mismatch; partial retained")
        if pinned and info["sha256"] != pinned["sha256"]:
            raise ValueError("Downloaded SHA256 differs from the pinned source; partial retained")
        partial.rename(path)
    else:
        info = digest_file(path)
        if info["bytes"] != length or info["md5_base64"] != expected:
            raise ValueError("Cached object differs from the official generation; use a new directory")
        if pinned and info["sha256"] != pinned["sha256"]:
            raise ValueError("Cached SHA256 differs from the pinned source")
    return dict(url=url, generation=generation, **info)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-synapses", type=int, default=3)
    parser.add_argument("--side-policy", choices=["official-row-fallback", "upstream-column-only"], default="official-row-fallback")
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix(".provenance.json").exists():
        raise FileExistsError("Choose a new native graph output path")
    if args.out.suffix != ".npz" or args.min_synapses < 1:
        raise ValueError("Use .npz output and a positive minimum synapse count")
    import flydrones
    from flydrones.brain.connectome import MALECNS_BASE, MALECNS_FILES, build_malecns
    from .benchmark_adapters import verified_revision
    from .flydrones_network import weight_hash, array_hash
    revision = verified_revision("flydrones", flydrones.__file__)
    pinned = json.loads(Path(__file__).with_name("flydrones_network_sources.json").read_text())
    if revision != pinned["upstream_revision"]:
        raise ValueError("Builder revision differs from the pinned data manifest")
    sources = {}
    for name, filename in MALECNS_FILES.items():
        sources[name] = fetch_file(MALECNS_BASE+"/"+filename, args.data_dir/filename, pinned["sources"][name])
        print(f"Verified {name}: {sources[name]['bytes']/1e6:.1f} MB", flush=True)
    started = time.perf_counter()
    graph = build_malecns(args.data_dir, min_synapses=args.min_synapses)
    before = dict(weights=weight_hash(graph), body_ids=array_hash(graph.body_ids), types=array_hash(graph.types))
    if args.side_policy == "official-row-fallback":
        import pyarrow.feather as feather
        records = feather.read_table(args.data_dir/MALECNS_FILES["annotations"],
                                     columns=["bodyId", "type", "rootSide", "somaSide"]).to_pylist()
        annotation_side_fallback(graph, records)
    after = dict(weights=weight_hash(graph), body_ids=array_hash(graph.body_ids), types=array_hash(graph.types))
    if before != after:
        raise AssertionError("Side metadata compatibility changed weights, IDs or cell types")
    seconds = time.perf_counter()-started
    graph.save(args.out)
    result = dict(upstream_revision=revision, sources=sources, graph=digest_file(args.out),
                  neurons=graph.n, directed_connections=graph.n_connections,
                  synapses_absolute_weight_sum=int(np.abs(graph.weights.data).sum(dtype=np.float64)),
                  native_float32_synapse_sum=graph.n_synapses, native_meta=graph.meta,
                  builder="Unmodified pinned flydrones.brain.connectome.build_malecns",
                  compatibility_integrity=dict(before=before, after=after, unchanged=True),
                  build_seconds=seconds, scope="Full native filtered graph, no subgraph/core reduction")
    args.out.with_suffix(".provenance.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
