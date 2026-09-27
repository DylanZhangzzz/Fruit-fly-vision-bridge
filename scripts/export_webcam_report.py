"""Export aggregate evidence only; optionally replay two recorded inputs from reset.

Private images, per-channel rates, per-frame logs and device serials are not copied.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyvisionbridge.live_core import BrainClient


def export(run_dir,output,model_dir=None):
    summary=json.loads((run_dir/'summary.json').read_text(encoding='utf8'))
    rows=[json.loads(line) for line in (run_dir/'frames.jsonl').read_text(encoding='utf8').splitlines()]
    if not rows or len(rows)!=summary['frames']:
        raise ValueError('Need a completed, nonempty run with matching summary and log')
    keys=['run_id','camera','geometry','head_from_camera','brain','encoder','gain_hz',
          'sampled_L2','frames','total_spikes','downstream_spikes','model_ms_total',
          'model_ms_per_update','wall_elapsed_s','skipped_camera_frames',
          'observed_mean_luminance_range','input_changed_between_frames','continuous_ticks',
          'frame_age_ms_p50_p95','clock','depth','imu','biological_response_validated']
    report={k:summary[k] for k in keys}
    report['capture_error_present']=summary.get('error') is not None
    report['privacy']='Aggregate only: no images, serials, per-channel inputs or per-frame logs'
    report['model_speed_ratio']=summary['model_ms_total']/1000/summary['wall_elapsed_s']
    report['controls']={name:{key:r[key] for key in ['model_ms','total_spikes','input_neuron_spikes','downstream_spikes']}
                        for name,r in summary['initial_controls']['runs'].items()}
    report['control_checks']=summary['initial_controls']['checks']
    if model_dir:
        replay={}
        with BrainClient(model_dir) as brain:
            for key in ['manifest_sha256','metadata_sha256','engine_sha256']:
                if brain.ready[key]!=summary['brain'][key]:raise ValueError('Replay model differs: '+key)
            for label,choose in [('lowest_mean_brightness',min),('highest_mean_brightness',max)]:
                row=choose(rows,key=lambda r:r['mean_luminance'])
                channels=[dict(bodyId=i,rate_hz=h) for i,h in zip(row['sampled_ids'],row['rates_hz'],strict=True)]
                result=brain.request('controls',channels=channels,steps=1000)
                replay[label]=dict(frame=row['frame'],mean_luminance=row['mean_luminance'],
                    mean_engineering_rate_hz=float(np.mean(row['rates_hz'])),
                    runs={name:{key:r[key] for key in ['model_ms','total_spikes','input_neuron_spikes','downstream_spikes']}
                          for name,r in result['runs'].items()})
        report['contrast_replay']=dict(selection='Post-hoc extrema of recorded mean brightness; not a held-out biological test',
            protocol='100 ms model time per condition; same initial state and seed; same engine/data hashes',inputs=replay)
        report['contrast_replay']['different_downstream_activity']=(
            replay['lowest_mean_brightness']['runs']['camera']['downstream_spikes']!=
            replay['highest_mean_brightness']['runs']['camera']['downstream_spikes'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_dir',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,help='Optional external model for reset-matched contrast replay')
    a=p.parse_args()
    result=export(a.run_dir,a.output,a.model_dir)
    print(json.dumps({k:result[k] for k in ['frames','sampled_L2','continuous_ticks','control_checks','model_speed_ratio']}))
