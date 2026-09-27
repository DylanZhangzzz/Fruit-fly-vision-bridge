import os
from pathlib import Path
"""Export actual PNG stimuli, then reload them through the production sampler.

This is a synthetic image-space test, not a camera/screen or fly calibration.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from encode_depth import ROOT, column_mapping, sample_channels

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'camera_lab/stimuli')
    p.add_argument('--validate',action='store_true')
    args=p.parse_args(); out=args.output; out.mkdir(parents=True,exist_ok=True)
    k=json.loads(((Path(os.environ.get('FLYVISION_LEGACY_CAPTURE', str(ROOT/'camera_lab/captures/legacy')))/'report.json')).read_text())['color_intrinsics']
    mapping=column_mapping(k); w,h=k['width'],k['height']
    manifest=[]
    for i,m in enumerate(mapping):
        u,v=round(m['u']),round(m['v'])
        a=np.full((h,w),255,np.uint8); a[v-1:v+2,u-1:u+2]=0
        name=f'{i:03d}_L2_{m["bodyId"]}.png'; Image.fromarray(a).save(out/name)
        manifest.append(dict(m,file=name,center_pixel=[u,v],dot_size_px=3))
    Image.new('L',(w,h),255).save(out/'white.png')
    Image.new('L',(w,h),0).save(out/'black.png')
    preview=Image.new('RGB',(w,h),'white'); draw=ImageDraw.Draw(preview)
    for m in mapping:
        u,v=round(m['u']),round(m['v']); draw.rectangle((u-1,v-1,u+1,v+1),fill='black')
    preview.save(out/'all_positions_preview.png')
    (out/'manifest.json').write_text(json.dumps(dict(scope='Synthetic virtual-image coordinates; no physical display calibration',intrinsics=k,stimuli=manifest),indent=2),encoding='utf-8')
    if not args.validate:
        print(f'Generated {len(manifest)} stimuli in {out}'); return
    depth=np.ones((h,w),np.float32); response=np.zeros((len(mapping),len(mapping)),np.float32); records=[]
    for i,m in enumerate(manifest):
        rgb=np.asarray(Image.open(out/m['file']).convert('RGB'),dtype=np.float32)/255
        rates=np.array([c['rate_hz'] for c in sample_channels(rgb,depth,mapping)])
        response[i]=rates; winners=np.flatnonzero(np.isclose(rates,rates.max(),atol=1e-5,rtol=0))
        records.append(dict(bodyId=m['bodyId'],file=m['file'],target_hit=i in winners,
                            isolated=len(winners)==1 and i in winners,
                            peak_ids=';'.join(mapping[j]['bodyId'] for j in winners),rate_hz=float(rates[i])))
        if (i+1)%100==0:print(f'PNG replay {i+1}/{len(mapping)}',flush=True)
    def rates_for(name,z):
        rgb=np.asarray(Image.open(out/name).convert('RGB'),dtype=np.float32)/255
        return np.array([c['rate_hz'] for c in sample_channels(rgb,z,mapping)])
    white_max=float(rates_for('white.png',depth).max())
    invalid_max=float(rates_for('black.png',np.full_like(depth,np.nan)).max())
    # Frozen previous audit is an independent saved result, not biological ground truth.
    reference=np.load(ROOT/'camera_lab/validation/local_stimulus_response.npy')
    difference=float(np.max(np.abs(response-reference)))
    with (out/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=records[0]); writer.writeheader(); writer.writerows(records)
    np.save(out/'response.npy',response)
    summary=dict(tested=len(records),target_hits=sum(r['target_hit'] for r in records),
                 isolated=sum(r['isolated'] for r in records),white_max_hz=white_max,
                 invalid_depth_max_hz=invalid_max,previous_response_max_difference_hz=difference,
                 biological_calibration='UNVERIFIED',physical_screen_camera_calibration='NOT_PERFORMED')
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary))
    assert all(r['target_hit'] for r in records) and white_max<1e-6 and invalid_max==0 and difference<1e-5

if __name__=='__main__':main()
