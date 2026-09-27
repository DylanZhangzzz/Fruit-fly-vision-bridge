"""Join published left-eye L2 body IDs to the author's left-eye angle table.

No mirror of the right-eye map and no nearest-neighbour ID assignment are used.
"""
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
SOURCE=BASE/'source'
ANGLE_COMMIT='503c7f055d5491a48b60b49ade8c71798d24d8f1'
COLUMN_COMMIT='23f6ac131529b5f56894c6eeb9b88b17894fc00d'
DATASET='eyemap_mcns_f20240701'
ANGLES=SOURCE/f'eyemap_archive/maps/{DATASET}/pqxyztp_left.xlsx'
COLUMNS=SOURCE/'visualpathways/ME_L_columnar-cells_location.xlsx'
INVENTORY=SOURCE/'malecns_l2_inventory.json'
ANGLE_URL=f'https://github.com/artxz/eyemap-archive/blob/{ANGLE_COMMIT}/maps/{DATASET}/pqxyztp_left.xlsx'
COLUMN_URL=f'https://github.com/reiserlab/visualpathways/blob/{COLUMN_COMMIT}/params/ME_L_columnar-cells_location.xlsx'
STATUS='AUTHOR_PUBLISHED_COLUMN_CORRESPONDENCE'


def validate_angles(table):
    if table.duplicated(['hex1','hex2']).any():raise ValueError('Duplicate left-eye column key')
    if not ((table.p==table.hex2-19)&(table.q==table.hex1-18)).all():raise ValueError('Hex/pq convention mismatch')
    v=table[['x','y','z']].to_numpy(float)
    if not np.isfinite(v).all() or not np.allclose(np.linalg.norm(v,axis=1),1,atol=1e-8):raise ValueError('Invalid unit rays')
    if not np.allclose(np.degrees(np.arccos(v[:,2])),table.theta,atol=1e-7):raise ValueError('Colatitude mismatch')
    if not np.allclose(-np.degrees(np.arctan2(v[:,1],v[:,0])),table.phi,atol=1e-7):raise ValueError('Azimuth convention mismatch')


def build_left_mapping(columns,angles,inventory):
    validate_angles(angles)
    if columns.duplicated(['hex1_id','hex2_id']).any():raise ValueError('Duplicate column assignment key')
    known={r['bodyId']:r for r in inventory}
    if len(known)!=len(inventory):raise ValueError('Duplicate inventory ID')
    assigned={}
    for row in columns.itertuples():
        if pd.isna(row.L2):continue
        for token in str(row.L2).replace(';',',').split(','):
            n=Decimal(token.strip())
            if not n.is_finite() or n!=n.to_integral_value():raise ValueError('Noninteger body ID')
            body=str(int(n));identity=known.get(body)
            if identity is None or identity['type']!='L2' or identity['eye']!='L':
                raise ValueError('Column body ID is not a model left-eye L2: '+body)
            if body in assigned:raise ValueError('Ambiguous body-to-column assignment: '+body)
            h=(int(row.hex1_id),int(row.hex2_id))
            if h!=(row.hex1_id,row.hex2_id):raise ValueError('Noninteger hex coordinate')
            assigned[body]=h
    lookup={(int(r.hex1),int(r.hex2)):r for r in angles.itertuples()}
    output=[]
    for identity in sorted(inventory,key=lambda r:int(r['bodyId'])):
        if identity['type']!='L2' or identity['eye']!='L':continue
        body=identity['bodyId'];key=assigned.get(body)
        row=dict(bodyId=body,eye='L',type='L2',hex1=None,hex2=None,
            reference_id=None,ray_head_xyz=None,evidence=ANGLE_URL,column_evidence=COLUMN_URL)
        if key is None:row['status']='MISSING_AUTHOR_COLUMN_ASSIGNMENT'
        else:
            row.update(hex1=key[0],hex2=key[1]);a=lookup.get(key)
            if a is None:row['status']='MISSING_AUTHOR_BOUNDARY_COLUMN'
            else:row.update(status=STATUS,reference_id=f'{DATASET}:L:{key[0]}:{key[1]}',
                ray_head_xyz=[a.x,a.y,a.z],azimuth_left_deg=-a.phi,elevation_deg=90-a.theta,
                source_p=int(a.p),source_q=int(a.q))
        output.append(row)
    return output


def main():
    inventory=json.loads(INVENTORY.read_text(encoding='utf8'))
    rows=build_left_mapping(pd.read_excel(COLUMNS),pd.read_excel(ANGLES),inventory['neurons'])
    right=json.loads((BASE/'data/malecns_author_crosswalk.json').read_text())
    right_ids={r['bodyId'] for r in inventory['neurons'] if r['eye']=='R' and r['type']=='L2'}
    if {r['bodyId'] for r in right}!=right_ids:raise ValueError('Right mapping and model inventory disagree')
    counts=Counter(r['status'] for r in rows)
    report=dict(eye='L',target_L2=len(rows),resolved_L2=counts[STATUS],
        resolved_unique_columns=len({(r['hex1'],r['hex2']) for r in rows if r['status']==STATUS}),
        status_counts=dict(counts),missing_assignment_ids=[r['bodyId'] for r in rows if r['hex1'] is None],
        angle_source=ANGLE_URL,column_source=COLUMN_URL,model_inventory_source=inventory['source'],
        model_metadata_sha256=inventory['source_sha256'],
        join='Exact left-eye body ID -> (hex1,hex2) -> published left-eye ray; no mirroring or fitted registration',
        axes='x forward, y left, z up; azimuth_left=-source_phi; elevation=90-source_theta',
        biological_status='Author-published anatomical cross-specimen estimate, not physiological ground truth',
        limitations=['Unassigned IDs and unpublished boundary directions stay unknown',
            'Left column assignment has one published assignment source plus model identity/side checks; not two independent column measurements',
            'A monocular webcam supplies a common camera origin; distinct eye origins/stereo disparity are not reconstructed'],
        source_sha256={p.relative_to(BASE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [ANGLES,COLUMNS,INVENTORY]})
    for name,value in [('malecns_left_crosswalk.json',rows),('left_mapping_report.json',report)]:
        (BASE/'data'/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
