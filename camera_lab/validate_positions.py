import os
from pathlib import Path
"""Exhaustive input-map audit, intentionally separate from biological validation."""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyrealsense2 as rs

from encode_depth import ROOT, column_mapping, sample_channels, project_points

CAPTURE=Path(os.environ.get('FLYVISION_LEGACY_CAPTURE', str(ROOT/'camera_lab/captures/legacy')))
OUT=ROOT/'camera_lab/validation'


def main():
    OUT.mkdir(exist_ok=True)
    report=json.loads((CAPTURE/'report.json').read_text())
    k=report['color_intrinsics']
    mapping=column_mapping(k)
    neurons=json.load(gzip.open(ROOT/'fruit-fly-simulation/public/data/neurons.json.gz','rt'))
    byid={str(r[0]):r for r in neurons}
    reference={c['bodyId']:c for c in json.loads((CAPTURE/'neural_input.json').read_text())['channels']}
    groups=defaultdict(list)
    for c in mapping:
        groups[c['hex1'],c['hex2']].append(c['bodyId'])
    white=np.ones((k['height'],k['width'],3),dtype=np.float32)
    depth=np.ones(white.shape[:2],dtype=np.float32)
    baseline=np.array([r['rate_hz'] for r in sample_channels(white,depth,mapping)])
    assert np.max(np.abs(baseline))<1e-6
    empty=np.full_like(depth,np.nan)
    assert all(c['rate_hz']==0 for c in sample_channels(white*0,empty,mapping))
    # Mutation control: deliberately give each neuron the next neuron's location.
    shuffled=[dict(m,u=mapping[(i+1)%len(mapping)]['u'],v=mapping[(i+1)%len(mapping)]['v'])
              for i,m in enumerate(mapping)]
    rows=[]
    response=np.zeros((len(mapping),len(mapping)),dtype=np.float32)
    for i,c in enumerate(mapping):
        u,v=int(round(c['u'])),int(round(c['v']))
        white[v-1:v+2,u-1:u+2]=0
        activity=np.array([x['rate_hz'] for x in sample_channels(white,depth,mapping)])
        white[v-1:v+2,u-1:u+2]=1
        response[i]=activity
        winners=np.flatnonzero(activity>activity.max()-1e-5)
        ids=[mapping[j]['bodyId'] for j in winners]
        duplicate=groups[c['hex1'],c['hex2']]
        # Frozen prior coordinates catch accidental refactor shifts; they do NOT
        # validate anatomical orientation or field-of-view calibration.
        ref=reference[c['bodyId']]
        frozen_error=float(np.hypot(c['u']-ref['u'],c['v']-ref['v']))
        # Independent analytic inverse projection and RealSense SDK forward check.
        intr=rs.intrinsics()
        for key in ['width','height','fx','fy','ppx','ppy']:setattr(intr,key,k[key])
        intr.model=rs.distortion.none; intr.coeffs=[0]*5
        errors=[]
        for z in [0.2,0.35,1.0,3.0]:
            p=[(c['u']-k['ppx'])*z/k['fx']+0.03,(c['v']-k['ppy'])*z/k['fy'],z]
            actual=project_points(np.array([p]),0.03,k['fx'],k['fy'],k['ppx'],k['ppy'])[0]
            sdk=rs.rs2_project_point_to_pixel(intr,[p[0]-0.03,p[1],p[2]])
            errors.append(float(np.linalg.norm(actual-sdk)))
        rows.append(dict(bodyId=c['bodyId'],index=c['index'],hex1=c['hex1'],hex2=c['hex2'],
                         u=c['u'],v=c['v'],identity_ok=byid[c['bodyId']][1]=='L2' and byid[c['bodyId']][3]=='R',
                         inside_image=(6<=u<k['width']-6 and 6<=v<k['height']-6),
                         local_stimulus_hits_target=c['bodyId'] in ids,
                         isolated_position=len(ids)==1 and ids[0]==c['bodyId'],
                         tied_bodyIds=';'.join(ids),shared_column_ids=';'.join(duplicate) if len(duplicate)>1 else '',
                         target_rate_hz=float(activity[i]),frozen_position_error_px=frozen_error,
                         sdk_projection_max_error_px=max(errors),
                         camera_depth_available=ref['depth_m'] is not None,
                         biological_visual_field='UNVERIFIED',
                         status='AMBIGUOUS_SHARED_COLUMN' if len(duplicate)>1 else 'ENGINEERING_PASS_ONLY'))
        if (i+1)%100==0:print(f'{i+1}/{len(mapping)}',flush=True)
    # Reassigning map positions permutes input responses exactly; no neural
    # connections are involved in this negative control.
    shuffled_correct=int(sum(np.argmax(response[i,np.roll(np.arange(len(mapping)),-1)])==i for i in range(len(mapping))))
    input_sha=hashlib.sha256((ROOT/'camera_lab/data/ME_assigned_columns.csv').read_bytes()).hexdigest()
    right_l2={str(r[0]) for r in neurons if r[1]=='L2' and r[3]=='R'}
    used={r['bodyId'] for r in mapping}
    summary=dict(neurons=len(mapping),unique_ids=len(used),unique_columns=len(groups),
                 source_table_sha256=input_sha,missing_right_L2_ids=sorted(right_l2-used),
                 shared_columns={str(key):value for key,value in groups.items() if len(value)>1},
                 isolated_position_pass=sum(r['isolated_position'] for r in rows),
                 target_in_peak_set=sum(r['local_stimulus_hits_target'] for r in rows),
                 baseline_max_rate=float(baseline.max()),shuffled_top1_correct=shuffled_correct,
                 current_capture_depth_available=sum(r['camera_depth_available'] for r in rows),
                 max_sdk_projection_error_px=max(r['sdk_projection_max_error_px'] for r in rows),
                 scope='893 local 3x3 dark patches on white field, same production sampler; geometry at four depths. Does not test neural propagation or prove anatomical visual-field orientation.',
                 biological_calibration='UNVERIFIED',
                 scope_exclusions=['Network controls are in network_summary.json',
                                   'RGB-D calibration audit is in calibration_summary.json',
                                   'Flip/scale/shift controls are in mutation_summary.json',
                                   'Biological angular mapping remains unverified'])
    with (OUT/'neurons.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    np.save(OUT/'local_stimulus_response.npy',response)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    assert all(r['identity_ok'] and r['inside_image'] and r['local_stimulus_hits_target'] for r in rows)
    assert summary['max_sdk_projection_error_px']<0.001


if __name__=='__main__':main()
