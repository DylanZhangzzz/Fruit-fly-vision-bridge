"""Exact MaleCNS column join to the eyemap_T4 maintainer's published angle table.

Derived data: CC BY-SA 4.0, Arthur Zhao / eyemap-archive. No fitting or
nearest-neighbour substitutions; missing boundary columns stay unresolved.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
COMMIT = '503c7f055d5491a48b60b49ade8c71798d24d8f1'
DATASET = 'eyemap_mcns_f20240701'
SOURCE = BASE/'source/eyemap_archive'
XLSX = SOURCE/f'maps/{DATASET}/pqxyztp_right.xlsx'
URL = f'https://github.com/artxz/eyemap-archive/blob/{COMMIT}/maps/{DATASET}/pqxyztp_right.xlsx'
STATUS = 'AUTHOR_PUBLISHED_COLUMN_CORRESPONDENCE'


def join_columns(targets, table):
    if table.duplicated(['hex1', 'hex2']).any():
        raise ValueError('Ambiguous author column keys')
    if not ((table.p == table.hex2-19) & (table.q == table.hex1-18)).all():
        raise ValueError('Author hex/pq convention mismatch')
    v = table[['x', 'y', 'z']].to_numpy(float)
    if not np.isfinite(v).all() or not np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-8):
        raise ValueError('Invalid author directions')
    if not np.allclose(np.degrees(np.arccos(v[:, 2])), table.theta, atol=1e-7):
        raise ValueError('Colatitude mismatch')
    # Source phi is RIGHT-positive, whereas our head azimuth is LEFT-positive.
    if not np.allclose(-np.degrees(np.arctan2(v[:, 1], v[:, 0])), table.phi, atol=1e-7):
        raise ValueError('Azimuth convention mismatch')
    lookup = {(int(r.hex1), int(r.hex2)): r for r in table.itertuples()}
    out = []
    for target in targets:
        r = dict(target)
        s = lookup.get((r['hex1'], r['hex2']))
        if not r['source_column_agrees']:
            raise ValueError('Body ID column assignment disagrees between sources')
        if s is not None:
            r.update(reference_id=f'{DATASET}:R:{r["hex1"]}:{r["hex2"]}',
                     ray_head_xyz=[s.x, s.y, s.z],
                     azimuth_left_deg=-s.phi, elevation_deg=90-s.theta,
                     status=STATUS, evidence=URL,
                     source_p=int(s.p), source_q=int(s.q))
        else:
            r.update(reference_id=None, ray_head_xyz=None,
                     status='MISSING_AUTHOR_BOUNDARY_COLUMN', evidence=URL)
        out.append(r)
    if len({r['bodyId'] for r in out}) != len(out):
        raise ValueError('Duplicate target body IDs')
    return out


def main():
    targets=json.loads((BASE/'data/malecns_crosswalk.json').read_text())
    table=pd.read_excel(XLSX)
    rows=join_columns(targets, table)
    resolved=[r for r in rows if r['status']==STATUS]
    groups={}
    for r in resolved: groups.setdefault((r['hex1'],r['hex2']),[]).append(r['bodyId'])
    report=dict(author_archive_commit=COMMIT, source_url=URL, source_license='CC BY-SA 4.0',
                author_rows=len(table), target_L2=len(rows), resolved_L2=len(resolved),
                resolved_unique_columns=len(groups), missing_L2=len(rows)-len(resolved),
                duplicate_columns=[dict(hex=list(k),bodyIds=v) for k,v in groups.items() if len(v)>1],
                axes='x forward, y left, z up; azimuth_left=-source_phi; elevation=90-source_theta',
                join='Exact (right eye, hex1, hex2); author file includes hex keys; no fitted registration',
                biological_status='Published anatomical cross-specimen estimate, not physiological ground truth',
                limitations=['46 boundary columns have no published direction in this table; no extrapolation',
                             'Original 778 FAFB reference rows are a different product, not MaleCNS neuron IDs',
                             'Archive generation pipeline R_eyemap-DIY is private; published outputs are available',
                             'Camera mounting and L2 response model remain engineering assumptions'],
                source_sha256={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in SOURCE.rglob('*') if p.is_file()})
    (BASE/'data/malecns_author_crosswalk.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (BASE/'data/author_mapping_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2))


if __name__=='__main__': main()
