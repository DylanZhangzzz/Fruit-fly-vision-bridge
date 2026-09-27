import os
from pathlib import Path
"""Independent box-overlap oracle and injected spatial mapping faults."""
import json
import numpy as np
from encode_depth import ROOT,column_mapping,sample_channels

def response_oracle(stimuli,receivers):
    # 3x3 black stimulus, 13x13 receiver, white background and valid depth.
    lo=np.maximum(stimuli[:,None,:]-1,receivers[None,:,:]-6)
    hi=np.minimum(stimuli[:,None,:]+1,receivers[None,:,:]+6)
    area=np.prod(np.maximum(0,hi-lo+1),axis=2)
    return 120*area/169

def main():
    out=ROOT/'camera_lab/validation'
    k=json.loads(((Path(os.environ.get('FLYVISION_LEGACY_CAPTURE', str(ROOT/'camera_lab/captures/legacy')))/'report.json')).read_text())['color_intrinsics']
    mapping=column_mapping(k)
    positions=np.rint([[c['u'],c['v']] for c in mapping]).astype(int)
    observed=np.load(out/'local_stimulus_response.npy')
    oracle=response_oracle(positions,positions)
    error=float(abs(oracle-observed).max())
    assert error<1e-5
    variants={
        'horizontal_flip':np.column_stack([k['width']-1-positions[:,0],positions[:,1]]),
        'vertical_flip':np.column_stack([positions[:,0],k['height']-1-positions[:,1]]),
        'scale_0.8':np.rint((positions-[320,240])*0.8+[320,240]).astype(int),
        'shift_7px_x':positions+[7,0],
        'cyclic_neuron_shuffle':np.roll(positions,-1,axis=0)}
    results={}
    for name,p in variants.items():
        faulty=response_oracle(positions,p)
        changed=abs(faulty-oracle).max(axis=1)>1e-5
        results[name]={'affected_stimulus_positions':int(changed.sum()),
                       'unchanged_positions':int((~changed).sum())}
        assert changed.sum()>800
        # Verify representative mutated maps through the actual production sampler,
        # independently of the analytic all-pairs oracle.
        altered=[dict(c,u=float(q[0]),v=float(q[1])) for c,q in zip(mapping,p)]
        image=np.ones((480,640,3),np.float32);depth=np.ones((480,640),np.float32)
        max_diff=0
        for i in [0,177,446,700,892]:
            u,v=positions[i];image[v-1:v+2,u-1:u+2]=0
            rates=np.array([r['rate_hz'] for r in sample_channels(image,depth,altered)])
            image[v-1:v+2,u-1:u+2]=1
            max_diff=max(max_diff,float(abs(rates-faulty[i]).max()))
        assert max_diff<1e-5
        results[name]['production_spotcheck_max_error_hz']=max_diff
    summary={'all_pairs_oracle_max_error_hz':error,'mutations':results,
             'scope':'Fault detection relative to current declared camera-grid convention. Cannot determine the biologically correct orientation.',
             'boundary_check':'All current 13x13 sample windows fit within image; boundary unknowns need visual-field calibration.'}
    (out/'mutation_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
