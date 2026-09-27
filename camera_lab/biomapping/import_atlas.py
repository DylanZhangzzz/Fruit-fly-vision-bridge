"""Import published reference-eye directions without inventing MaleCNS matches."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import rdata

BASE=Path(__file__).resolve().parent
COMMIT='99d2a43123db636cedb55af9ff31a59657e7d17e'

def main():
    src=BASE/'source'; out=BASE/'data';out.mkdir(exist_ok=True)
    d=rdata.read_rda(src/'eyemap.RData'); med=np.asarray(rdata.read_rda(src/'med_ixy.RData')['med_ixy'])
    pairs=np.asarray(d['eyemap']); rays=np.asarray(d['ucl_rot_sm'])
    assert len(pairs)==len(rays)==778 and np.isfinite(rays).all()
    assert np.max(abs(np.linalg.norm(rays,axis=1)-1))<1e-6
    assert np.array_equal(np.array(d['ucl_rot_sm'].coords['dim_0'],int),pairs[:,1].astype(int))
    grid={int(row[0]):row[1:] for row in med}; rows=[]
    for (mi,lens),v in zip(pairs,rays):
        q=grid[int(mi)]
        rows.append(dict(reference_id=f'Zhao2025_Mi1_index_{int(mi)}',mi1_source_index=int(mi),
                         lens_source_index=int(lens),grid_p=int(q[0]),grid_q=int(q[1]),
                         ray_x_forward=v[0],ray_y_left=v[1],ray_z_up=v[2],
                         azimuth_left_deg=float(np.degrees(np.arctan2(v[1],v[0]))),
                         elevation_deg=float(np.degrees(np.arcsin(v[2]))),
                         eye='R',status='PUBLISHED_REFERENCE_CROSS_SPECIMEN_MAP'))
    with (out/'reference_rays.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    # Audit a second MaleCNS source by exact body ID, never by row order.
    source=pd.read_excel(src/'visualpathways/ME_columnar-cells_location.xlsx')
    identities={}
    for _,r in source.iterrows():
        for token in str(r['L2']).replace(';',',').split(','):
            try:bid=str(int(float(token.strip())))
            except ValueError:continue
            identities.setdefault(bid,[]).append([int(r['hex1_id']),int(r['hex2_id'])])
    original=list(csv.DictReader((BASE.parent/'data/ME_assigned_columns.csv').open()))
    original=[r for r in original if r['neuron_type']=='L2']
    crosswalk=[]
    for r in original:
        position=[int(r['assigned_hex1']),int(r['assigned_hex2'])]
        crosswalk.append(dict(bodyId=r['bodyId'],hex1=position[0],hex2=position[1],
                              other_source_columns=identities.get(r['bodyId'],[]),
                              source_column_agrees=position in identities.get(r['bodyId'],[]),
                              reference_id=None,ray_head_xyz=None,
                              status='UNRESOLVED_MALECNS_TO_REFERENCE',evidence=None))
    (out/'malecns_crosswalk.json').write_text(json.dumps(crosswalk,indent=2),encoding='utf-8')
    report=dict(reference_count=len(rows),malecns_L2_count=len(crosswalk),resolved_malecns_angles=0,
                second_source_column_agrees=sum(r['source_column_agrees'] for r in crosswalk),
                reference_commit=COMMIT,visualpathways_commit='23f6ac131529b5f56894c6eeb9b88b17894fc00d',
                axes='right-handed: x anterior/forward, y left, z dorsal/up; positive azimuth left',
                evidence=['proc_uCT.R: mrot=cbind(vf,vleft,vn)',
                          'Fig_0.R: eyemap, med_xyz, ucl_rot_sm share row order',
                          'proc_eyemap.R: manual equator/meridian grid correspondence'],
                limitations=['Reference Mi1 indices are NOT MaleCNS body IDs',
                             'Source mapping combines EM and microCT specimens; not every ray is a direct physiological measurement',
                             'Separate lens_ixy.RData has a different row count than embedded lens_ixy; not mixed',
                             'No established MaleCNS to reference-angle correspondence in inspected files'],
                source_sha256={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()})
    (out/'provenance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2))

if __name__=='__main__':main()
