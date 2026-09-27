"""RGB-D-IMU replay on published reference eye. No MaleCNS brain injection."""
import argparse
import csv
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import pyrealsense2 as rs
from geometry import project_rays,sample_rgb,rotation_flow,ASSUMED_HEAD_FROM_CAMERA,require_resolved_crosswalk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from encode_depth import zbuffer

BASE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path)
    p.add_argument('--malecns',action='store_true',help='Use author-published MaleCNS columns; emit engineered L2 input')
    args=p.parse_args();cap=args.capture
    meta=json.loads((cap/'report.json').read_text());imu=json.loads((cap/'imu.json').read_text())
    rows=list(csv.DictReader((BASE/'data/reference_rays.csv').open()))
    rays=np.array([[float(r[k]) for k in ['ray_x_forward','ray_y_left','ray_z_up']] for r in rows])
    if args.malecns:
        from import_author_map import STATUS
        crosswalk=json.loads((BASE/'data/malecns_author_crosswalk.json').read_text())
        rows=[r for r in crosswalk if r['status']==STATUS]
        rays=np.asarray([r['ray_head_xyz'] for r in rows])
    k=meta['color_intrinsics']
    if any(k['coeffs']):raise ValueError('Reference replay currently needs rectified/zero-distortion color intrinsics')
    rgb=np.asarray(Image.open(cap/'rgb.png'),dtype=float)/255
    uv,visible=project_rays(rays,k);colors=sample_rgb(rgb,uv,visible)
    # Native depth -> true color coordinates, without treating aligned Z as color Z.
    raw=np.asarray(Image.open(cap/'depth_raw_u16.png'));di=meta['depth_intrinsics'];intr=rs.intrinsics()
    for key in ['width','height','fx','fy','ppx','ppy']:setattr(intr,key,di[key])
    intr.model=getattr(rs.distortion,di['model'].split('.')[-1]);intr.coeffs=di['coeffs']
    z=raw*meta['depth_scale_m']; yy,xx=np.nonzero((z>=.15)&(z<=5))
    xyz=np.array([rs.rs2_deproject_pixel_to_point(intr,[float(x),float(y)],float(z[y,x])) for x,y in zip(xx,yy)])
    ext=meta['depth_to_color'];R=np.array(ext['rotation']).reshape(3,3,order='F');t=np.array(ext['translation_m'])
    xyz=xyz.reshape(-1,3)@R.T+t
    _,depth=zbuffer(xyz,np.zeros_like(xyz),0,k)
    timing=meta['frames_timing'][-1];clock=timing['color_clock'];stamp=timing['color_ms']
    packet={};flows=np.full_like(rays,np.nan)
    for name in ['accel','gyro']:
        all_samples=[s for s in imu if s['stream']==f'stream.{name}' and s['domain']==clock]
        samples=[s for s in all_samples if abs(s['timestamp_ms']-stamp)<=50]
        alignment='MATCHED_SDK_TIMESTAMP_DOMAIN'
        field='timestamp_ms';target_time=stamp
        if not samples and 'host_receipt_ms' in timing:
            field='host_receipt_ms';target_time=timing[field]
            samples=[s for s in imu if s['stream']==f'stream.{name}' and field in s and abs(s[field]-target_time)<=50]
            alignment='APPROXIMATE_HOST_RECEIPT_TIME_UNCALIBRATED_LATENCY'
        if not samples:
            packet[name]={'status':'NO_TIME_ALIGNED_SAMPLE'};continue
        rot=np.array(meta['imu_extrinsics'][name]['rotation']).reshape(3,3,order='F')
        value=rot@np.mean([s['xyz'] for s in samples],axis=0)
        packet[name]=dict(status='TIME_WINDOW_MATCHED_UNCALIBRATED',samples=len(samples),
                          alignment=alignment,nearest_dt_ms=min(abs(s[field]-target_time) for s in samples),color_xyz=value.tolist())
        if name=='gyro':flows=rotation_flow(rays,value)
    channels=[]
    for i,r in enumerate(rows):
        dep=None
        if visible[i]:
            x,y=np.rint(uv[i]).astype(int);patch=depth[max(0,y-1):y+2,max(0,x-1):x+2]
            valid=patch[np.isfinite(patch)&(patch>0)]
            if len(valid)>=3:dep=float(np.median(valid))
        lum=float(colors[i]@np.array([.2126,.7152,.0722])) if visible[i] else None
        channels.append(dict(reference_id=r['reference_id'],azimuth_left_deg=float(r['azimuth_left_deg']),
             elevation_deg=float(r['elevation_deg']),rgb_status='OBSERVED' if visible[i] else 'OUTSIDE_CAMERA_FOV',
             luminance=lum,depth_color_z_m=dep,depth_status='MEASURED_UNVERIFIED' if dep is not None else 'UNKNOWN',
             predicted_rotation_flow_head_per_s=flows[i].tolist() if np.isfinite(flows[i]).all() else None,
             malecns_bodyId=r['bodyId'] if args.malecns else None,
             brain_rate_hz=120*(1-lum) if args.malecns and lum is not None else None))
    out=cap/('malecns_eye' if args.malecns else 'reference_eye');out.mkdir(exist_ok=True)
    crosswalk=json.loads((BASE/'data/malecns_crosswalk.json').read_text())
    try:require_resolved_crosswalk(crosswalk)
    except ValueError as e:gate=str(e)
    else:gate='CORRESPONDENCE_PRESENT_BUT_RESPONSE_MODEL_STILL_REQUIRED'
    if args.malecns:gate='AUTHOR_PUBLISHED_847_L2; 46_UNRESOLVED_EXCLUDED; ENGINEERED_RESPONSE_ONLY'
    same=clock==timing['depth_clock']
    report=dict(reference_rays=len(rows),rgb_observed=int(visible.sum()),
                depth_observed=sum(c['depth_color_z_m'] is not None for c in channels),
                physical_capture=str(cap.resolve()),imu=packet,
                rgb_depth_dt_ms=abs(stamp-timing['depth_ms']) if same else None,
                head_from_camera=ASSUMED_HEAD_FROM_CAMERA.tolist(),
                mounting='ASSUMED: camera forward aligned to eye-frame forward; not anatomical head/mount calibration',
                depth_role='Same-time geometry/occlusion reference; no direct distance-to-neural-rate channel',
                imu_role='Predicted rotational optic flow, not extra fly sensory neurons; no gyro bias correction or absolute yaw',
                neural_response='ENGINEERED 120*(1-luminance) Hz, not physiological L2 response' if args.malecns else 'NOT_IMPLEMENTED: luminance values, not validated photoreceptor or L2 responses',
                target_mapping_gate=gate,neural_injection_performed=False)
    (out/'channels.json').write_text(json.dumps(channels,indent=2),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if args.malecns:
        import gzip
        model=BASE.parents[1]/'fruit-fly-simulation/public/data'
        manifest=json.loads((model/'manifest.json').read_text())
        neurons=json.loads(gzip.decompress((model/manifest['metadata']).read_bytes()))
        ids={str(n[0]):(i,n) for i,n in enumerate(neurons)}
        inputs=[]
        for c in channels:
            if c['brain_rate_hz'] is None:continue
            idx,n=ids[c['malecns_bodyId']]
            if n[1]!='L2' or n[3]!='R':
                raise ValueError(f'Unexpected target metadata: {n}')
            inputs.append(dict(index=idx,bodyId=c['malecns_bodyId'],rate_hz=c['brain_rate_hz']))
        (out/'brain_input.json').write_text(json.dumps(dict(channels=inputs,
             mapping='author_published_exact_hex_join',response_model='engineered_inverse_luminance',
             missing_columns_policy='excluded',outside_fov_policy='excluded'),indent=2),encoding='utf-8')
    canvas=Image.new('RGB',(1040,600),'#101923');draw=ImageDraw.Draw(canvas)
    draw.text((30,15),'Published right-eye rays | grey: outside camera | color: observed RGB',fill='white')
    for a in range(-180,181,30):
        x=40+(a+180)/360*960;draw.line((x,50,x,530),fill='#334552');draw.text((x-10,540),str(a),fill='white')
    for e in range(-90,91,30):
        y=50+(90-e)/180*480;draw.line((40,y,1000,y),fill='#334552');draw.text((3,y),str(e),fill='white')
    for i,c in enumerate(channels):
        x=40+(c['azimuth_left_deg']+180)/360*960;y=50+(90-c['elevation_deg'])/180*480
        color=tuple(np.clip(colors[i]*255,0,255).astype(int)) if visible[i] else '#657887'
        draw.ellipse((x-3,y-3,x+3,y+3),fill=color)
    draw.text((30,575),'Azimuth positive LEFT; elevation positive UP. '+('Author MaleCNS column mapping; 46 missing columns excluded.' if args.malecns else 'FAFB reference eye only.'),fill='white')
    canvas.save(out/'reference_coverage.png')
    (out/'index.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>生物参考眼回放</title>
<style>body{{background:#101923;color:#eef4fa;font:17px system-ui;max-width:1100px;margin:30px auto;padding:20px;line-height:1.7}}img{{width:100%}}a{{color:#8bd8fa}}</style>
<h1>生物参考眼 · RGB / 深度 / IMU</h1><p>论文参考视线 {len(rows)} 条；当前 RGB 可观测 {int(visible.sum())} 条；其中有深度 {report['depth_observed']} 条。</p>
<p><b>MaleCNS 对应尚未解决，未向全脑注入刺激。</b>本图采用论文参考眼和明确声明的相机安装朝向假设；灰色为相机视野外，不是黑色刺激。未把整只复眼压缩进相机画面。</p>
<img src="reference_coverage.png"><p>RGB 提供亮度；深度提供空间与遮挡参考；同一采集记录中的 IMU 提供旋转光流预测。当前 IMU 未做偏置校正，预测仍待独立运动实验验证。</p>
<p><a href="report.json">运行报告</a> · <a href="channels.json">逐视线采样结果</a></p>''',encoding='utf-8')
    print(json.dumps(report,indent=2));print(out/'index.html')
    if args.malecns:
        html=(out/'index.html').read_text(encoding='utf-8')
        html=html.replace('生物参考眼','MaleCNS 作者映射').replace('论文参考视线','已匹配 L2')
        html=html.replace('MaleCNS 对应尚未解决，未向全脑注入刺激。','作者表已连接 847 个 L2（846 个视柱）；46 个边缘 L2 缺失角度，排除输入。')
        html=html.replace('本图采用论文参考眼','本图采用作者发布的 MaleCNS 角度表')
        html += '<p>亮度 → 120×(1−亮度) Hz 是工程刺激模型，尚非生理 L2 模型。全脑执行结果另见 <a href="brain_report.json">传播报告</a>；<a href="../../../data/author_mapping_report.json">来源审计</a>。</p>'
        (out/'index.html').write_text(html,encoding='utf-8')

if __name__=='__main__':main()
