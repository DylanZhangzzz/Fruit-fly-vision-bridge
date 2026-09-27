"""Validate binocular mapping and optionally replay a saved RGB image in BrainCPU.

This opens no camera. Reports contain aggregate counts, not the input image.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyvisionbridge import Frame,map_frame,load_eye_mapping
from flyvisionbridge.live_core import BrainClient,Rectifier,approximate_intrinsics,engineer_rates


def validate(image_path,intrinsics,model_dir=None):
    if image_path:
        rgb=np.asarray(Image.open(image_path).convert('RGB'))
    else:
        rgb=np.full((intrinsics['height'],intrinsics['width'],3),255,np.uint8)
        rgb[:,:intrinsics['width']//2]=0
    rectify=Rectifier(intrinsics);rgb=rectify.apply(rgb)
    rows=load_eye_mapping()
    mapped=rectify.mask_channels(map_frame(Frame(rgb,rectify.k,0,'SAVED_IMAGE_TIME_UNKNOWN' if image_path else 'SYNTHETIC'),rows))
    rates=engineer_rates(mapped)
    eyes={eye:[c for c in rates if c['eye']==eye] for eye in ['L','R']}
    report=dict(input_kind='previously captured RGB image; offline replay' if image_path else 'synthetic half-field image',
        opens_camera=False,geometry=intrinsics,biological_response_validated=False,
        eyes={eye:dict(target_L2=sum(r['eye']==eye for r in rows),
            resolved_L2=sum(r['eye']==eye and r['status']=='AUTHOR_PUBLISHED_COLUMN_CORRESPONDENCE' for r in rows),
            visible_L2=len(eyes[eye])) for eye in ['L','R']},
        source_status_counts={eye:dict(Counter(r['status'] for r in rows if r['eye']==eye)) for eye in ['L','R']},
        privacy='No images, per-ID input vectors, private paths or serials included')
    checks=dict(both_eyes_observed=all(eyes.values()),disjoint_body_ids=not ({c['bodyId'] for c in eyes['L']}&{c['bodyId'] for c in eyes['R']}),
        unknowns_not_driven=not ({c['bodyId'] for c in mapped['channels'] if c['rgb_status']!='OBSERVED'}&{c['bodyId'] for c in rates}))
    if model_dir:
        with BrainClient(model_dir) as brain:
            report['brain']=brain.ready;conditions={}
            for label,channels in [('both',rates),('left',eyes['L']),('right',eyes['R'])]:
                result=brain.request('controls',channels=channels,steps=1000)
                conditions[label]={name:{key:r[key] for key in ['model_ms','total_spikes','input_neuron_spikes','downstream_spikes','input_by_eye']}
                                   for name,r in result['runs'].items()}
                checks[label+'_drives_input']=result['runs']['camera']['input_neuron_spikes']>0
                checks[label+'_propagates']=result['runs']['camera']['downstream_spikes']>0
                checks[label+'_no_input_silent']=result['runs']['no_input']['total_spikes']==0
                checks[label+'_disconnected_downstream_silent']=result['runs']['connections_off']['downstream_spikes']==0
            report['controls']=conditions
            brain.request('reset')
            sequence=[brain.request('step',channels=channels,steps=200) for channels in [eyes['L'],eyes['R'],rates,[],rates]]
            checks['continuous_state_through_eye_switches']=all(a['tick_after']==b['tick_before'] for a,b in zip(sequence,sequence[1:]))
            report['stream_test']=[{k:r[k] for k in ['tick_before','tick_after','input_by_eye','total_spikes','downstream_spikes']} for r in sequence]
            try:
                wrong=[dict(eyes['L'][0],eye='R')]
                brain.request('step',channels=wrong,steps=200)
                checks['mislabeled_eye_rejected']=False
            except ValueError:checks['mislabeled_eye_rejected']=True
            after=brain.request('step',channels=[],steps=1)
            checks['rejected_command_did_not_advance_model']=after['tick_before']==sequence[-1]['tick_after']
    report['checks']=checks;report['all_checks_passed']=all(checks.values())
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path)
    geometry=p.add_mutually_exclusive_group(required=True)
    geometry.add_argument('--intrinsics',type=Path)
    geometry.add_argument('--assume-hfov',type=float)
    p.add_argument('--model-dir',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    size=Image.open(a.image).size if a.image else (640,480)
    k=json.loads(a.intrinsics.read_text()) if a.intrinsics else approximate_intrinsics(*size,a.assume_hfov)
    result=validate(a.image,k,a.model_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'eyes':result['eyes'],'checks':result['checks']},indent=2))
    raise SystemExit(0 if result['all_checks_passed'] else 1)
