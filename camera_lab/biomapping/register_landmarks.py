"""Fit an explicitly approximate cross-specimen map using documented landmarks.

CSV columns: bodyId,reference_id,split,evidence (split is train or holdout).
There is deliberately no default correspondence or generated biological anchor.
"""
import argparse
import csv
import json
from pathlib import Path
import cv2
import numpy as np

BASE=Path(__file__).resolve().parent

def fit_affine(source,target):
    A=np.c_[np.asarray(source,float),np.ones(len(source))]
    if len(source)<6 or np.linalg.matrix_rank(A)<3:raise ValueError('Need >=6 non-collinear training landmarks')
    T,_,_,_=np.linalg.lstsq(A,np.asarray(target,float),rcond=None)
    if np.linalg.cond(A)>1e5:raise ValueError('Poorly conditioned landmarks')
    return T

def interpolate_rays(query,grid,rays,max_grid_distance=1.5):
    grid=np.asarray(grid,float); rays=np.asarray(rays,float);out=[]
    hull=cv2.convexHull(grid.astype(np.float32)).reshape(-1,2)
    for q in np.asarray(query,float):
        if cv2.pointPolygonTest(hull,(float(q[0]),float(q[1])),False)<0:
            out.append(None);continue
        dist=np.linalg.norm(grid-q,axis=1);ix=np.argsort(dist)[:3]
        if dist[ix[0]]>max_grid_distance:out.append(None);continue
        if dist[ix[0]]<1e-8:v=rays[ix[0]]
        else:
            weight=1/np.maximum(dist[ix],1e-8)**2;v=np.sum(rays[ix]*weight[:,None],axis=0)
        out.append((v/np.linalg.norm(v)).tolist())
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('landmarks',type=Path);args=p.parse_args()
    with args.landmarks.open(encoding='utf-8-sig') as f:anchors=list(csv.DictReader(f))
    male=json.loads((BASE/'data/malecns_crosswalk.json').read_text());byid={r['bodyId']:r for r in male}
    with (BASE/'data/reference_rays.csv').open() as f:ref=list(csv.DictReader(f))
    byref={r['reference_id']:r for r in ref}
    if len({r['bodyId'] for r in anchors})!=len(anchors) or len({r['reference_id'] for r in anchors})!=len(anchors):
        raise ValueError('Landmarks must be distinct on each side')
    if any(not r['evidence'].strip() or r['split'] not in ['train','holdout'] for r in anchors):
        raise ValueError('Every anchor needs evidence and a declared split')
    train=[r for r in anchors if r['split']=='train'];held=[r for r in anchors if r['split']=='holdout']
    if len(held)<3:raise ValueError('Need >=3 independent held-out landmarks')
    xy=lambda r:[byid[r['bodyId']]['hex1'],byid[r['bodyId']]['hex2']]
    pq=lambda r:[float(byref[r['reference_id']]['grid_p']),float(byref[r['reference_id']]['grid_q'])]
    T=fit_affine([xy(r) for r in train],[pq(r) for r in train])
    grid=np.array([[float(r['grid_p']),float(r['grid_q'])] for r in ref])
    rays=np.array([[float(r[k]) for k in ['ray_x_forward','ray_y_left','ray_z_up']] for r in ref])
    predicted=interpolate_rays(np.c_[[xy(r) for r in held],np.ones(len(held))]@T,grid,rays)
    errors=[]
    for a,v in zip(held,predicted):
        truth=rays[ref.index(byref[a['reference_id']])]
        errors.append(None if v is None else float(np.degrees(np.arccos(np.clip(np.dot(v,truth),-1,1)))))
    passed=all(e is not None and e<=3 for e in errors)
    query=np.c_[[[r['hex1'],r['hex2']] for r in male],np.ones(len(male))]@T
    mapped=interpolate_rays(query,grid,rays)
    result=dict(status='APPROXIMATE_CANDIDATE' if passed else 'REJECTED_HELDOUT_ANGLES',
                grid_affine=T.tolist(),holdout_angular_errors_deg=errors,holdout_threshold_deg=3,
                correspondence_evidence=anchors,
                note='Threshold is an engineering screening choice. Affine/grid interpolation across specimens is not ground truth.',
                channels=[dict(bodyId=r['bodyId'],ray_head_xyz=v,status='INFERRED_CROSS_SPECIMEN' if v else 'OUTSIDE_REFERENCE_SUPPORT') for r,v in zip(male,mapped)],
                neural_injection_allowed=False)
    dest=args.landmarks.with_suffix('.candidate.json');dest.write_text(json.dumps(result,indent=2),encoding='utf-8');print(dest)

if __name__=='__main__':main()
