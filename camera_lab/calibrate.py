"""CLI: target, capture, solve, imu-add, imu-solve. All outputs stay local."""
import argparse
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
import numpy as np
from PIL import Image,ImageDraw
from calibration_core import PATTERN,detect,solve_camera,solve_imu,POSES

BASE=Path(__file__).resolve().parent/'calibration'

def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2),encoding='utf-8')

def target(args):
    out=BASE/'target'; out.mkdir(parents=True,exist_ok=True)
    # A4 portrait, 20 mm squares. Geometry kept in physical SVG units.
    elements=['<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">',
              '<rect width="210" height="297" fill="white"/>']
    for y in range(7):
        for x in range(9):
            if (x+y)%2==0:elements.append(f'<rect x="{15+x*20}" y="{40+y*20}" width="20" height="20" fill="black"/>')
    elements += ['<text x="15" y="20" font-size="4">8 x 6 internal corners / 20 mm squares</text>',
                 '<text x="15" y="200" font-size="4">Print 100%. Measure squares before capture.</text>',
                 '<path d="M15 220 H115 M15 217 V223 M115 217 V223" stroke="black" fill="none"/>',
                 '<text x="15" y="230" font-size="4">This reference line must measure 100 mm.</text></svg>']
    (out/'checkerboard_A4.svg').write_text('\n'.join(elements),encoding='utf-8')
    a=Image.new('RGB',(840,1188),'white'); d=ImageDraw.Draw(a)
    for y in range(7):
        for x in range(9):
            if (x+y)%2==0:d.rectangle((60+x*80,160+y*80,60+(x+1)*80-1,160+(y+1)*80-1),fill='black')
    a.save(out/'checkerboard_preview.png')
    (out/'print.html').write_text('''<!doctype html><meta charset="utf-8"><title>A4 标靶</title>
<style>@page{size:A4 portrait;margin:0}body{margin:0}img{width:210mm;height:297mm}p{padding:16px}@media print{p{display:none}}</style>
<p>打印选择 A4、100% / 实际大小，关闭页眉页脚。贴平硬板，测量单格应为 20 mm、参考线应为 100 mm。预览缩放不表示实际尺寸。</p><img src="checkerboard_A4.svg">''',encoding='utf-8')
    rects=''.join(f'<rect x="{x+1}" y="{y+1}" width="1" height="1"/>' for y in range(7) for x in range(9) if (x+y)%2==0)
    (out/'screen.html').write_text('''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>屏幕棋盘标靶</title>
<style>html,body{margin:0;background:white;width:100%;height:100%;font:16px system-ui}header{padding:12px;background:#e8edf2}button{padding:8px}svg{display:block;width:100%;height:calc(100% - 120px)}:fullscreen header{display:none}:fullscreen svg{height:100vh}</style>
<header><b>屏幕标定板 · 9×7 方格 / 8×6 内角点</b><p>点击全屏后，用尺子量棋盘从最左格边缘到最右格边缘的总宽，除以 9 得到实际格长。保持窗口、缩放、显示器不变；相机拍摄这块屏幕。Esc 退出。</p><button onclick="document.documentElement.requestFullscreen()">全屏展示</button></header>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 11 9" preserveAspectRatio="xMidYMid meet" aria-label="9乘7棋盘格"><rect width="11" height="9" fill="white"/><g fill="black">'''+rects+'''</g></svg></html>''',encoding='utf-8')
    save(out/'board.json',dict(inner_corners=PATTERN,squares=[9,7],nominal_square_mm=20,physical_size_verified=False))
    assert detect(np.asarray(a)) is not None
    print(out/'print.html')

def capture(args):
    from device_selection import select_serial
    args.serial=select_serial(args.serial)
    import cv2
    import pyrealsense2 as rs
    from probe_camera import intrinsics
    if not 1<=args.seconds<=120:raise ValueError('Capture duration must be 1..120 seconds')
    if not 5<=args.square_mm<=100:raise ValueError('Enter measured square length in mm')
    out=BASE/'sessions'/datetime.now().strftime('%Y%m%d-%H%M%S-%f'); out.mkdir(parents=True)
    meta=dict(serial=args.serial,square_mm=args.square_mm,physical_square_user_supplied=True,views=[],image_size=[640,480])
    if args.resume:
        previous_meta=json.loads((args.resume/'session.json').read_text())
        if previous_meta['serial']!=args.serial or previous_meta['square_mm']!=args.square_mm or previous_meta['image_size']!=[640,480]:
            raise ValueError('Resume requires matching device, resolution and measured square size')
        for i,v in enumerate(previous_meta['views']):
            for name in [v['rgb'],v['depth'],f'corners_{i:03d}.png']:
                source=args.resume/name
                if source.parent.resolve()!=args.resume.resolve():raise ValueError('Invalid source filename')
                shutil.copy2(source,out/name)
        meta=previous_meta
        meta['continued_from']=str(args.resume.resolve())
    accepted=[np.array(v['corners'],np.float32) for v in meta['views']]
    pipe=rs.pipeline(); cfg=rs.config(); cfg.enable_device(args.serial)
    cfg.enable_stream(rs.stream.color,640,480,rs.format.rgb8,30)
    cfg.enable_stream(rs.stream.depth,640,480,rs.format.z16,30)
    profile=pipe.start(cfg); checked=0; last=None
    try:
        cp=profile.get_stream(rs.stream.color); dp=profile.get_stream(rs.stream.depth)
        ext=dp.get_extrinsics_to(cp)
        if args.resume and (meta['color_intrinsics']!=intrinsics(cp) or meta['depth_intrinsics']!=intrinsics(dp)):
            raise ValueError('Factory intrinsics changed: use a new calibration dataset')
        meta.update(color_intrinsics=intrinsics(cp),depth_intrinsics=intrinsics(dp),
                    depth_scale_m=profile.get_device().first_depth_sensor().get_depth_scale(),
                    depth_to_color=dict(rotation=ext.rotation,translation_m=ext.translation))
        for _ in range(30):pipe.wait_for_frames(5000)
        start=time.monotonic()
        previous=None; stable_since=None; last_saved=start-2
        last_update=start; detected=0
        while time.monotonic()-start<args.seconds:
            frames=pipe.wait_for_frames(5000); color=frames.get_color_frame(); depth=frames.get_depth_frame()
            if not color or not depth:continue
            rgb=np.asanyarray(color.get_data()).copy(); c=detect(rgb); checked+=1; last=rgb
            now=time.monotonic()
            if c is not None:detected+=1
            if now-last_update>=5:
                Image.fromarray(rgb).save(out/'last_frame.png')
                print(f'Progress: total accepted={len(accepted)}, board detected={detected}/{checked}',flush=True)
                last_update=now
            if c is None:
                previous=None; stable_since=None
                continue
            motion=float(np.sqrt(np.mean((c-previous)**2))) if previous is not None else float('inf')
            if motion>0.65:stable_since=now
            previous=c.copy()
            if stable_since is None:stable_since=now
            if now-stable_since>=0.6 and now-last_saved>=1.5 and all(np.sqrt(np.mean((c-old)**2))>8 for old in accepted):
                last_saved=now
                idx=len(accepted); accepted.append(c)
                Image.fromarray(rgb).save(out/f'rgb_{idx:03d}.png')
                Image.fromarray(np.asanyarray(depth.get_data()).copy()).save(out/f'depth_{idx:03d}.png')
                annotated=rgb.copy(); cv2.drawChessboardCorners(annotated,PATTERN,c,True)
                Image.fromarray(annotated).save(out/f'corners_{idx:03d}.png')
                meta['views'].append(dict(rgb=f'rgb_{idx:03d}.png',depth=f'depth_{idx:03d}.png',corners=c.tolist(),
                    color_ms=color.get_timestamp(),depth_ms=depth.get_timestamp(),
                    color_clock=str(color.get_frame_timestamp_domain()),depth_clock=str(depth.get_frame_timestamp_domain())))
                save(out/'session.json',meta); print(f'Accepted {len(accepted)}; move board to another tilt/position',flush=True)
                if len(accepted)>=30:break
    finally:
        pipe.stop()
        if last is not None:Image.fromarray(last).save(out/'last_frame.png')
        meta.update(checked_frames=checked,status='READY_TO_SOLVE' if len(accepted)>=15 else 'NEEDS_MORE_VIEWS')
        save(out/'session.json',meta)
    print(json.dumps(dict(session=str(out),accepted=len(accepted),status=meta['status'])))

def solve(args):
    meta=json.loads((args.session/'session.json').read_text())
    result=solve_camera([np.array(v['corners'],np.float32) for v in meta['views']],meta['image_size'],meta['square_mm']/1000)
    result.update(serial=meta['serial'],source_session=str(args.session.resolve()))
    # Screen depth may be missing/biased: report measurements, never fill holes.
    result['depth_plane_check']=depth_check(args.session,meta,result)
    save(args.session/'camera_candidate.json',result); print(json.dumps(result,indent=2))

def depth_check(session,meta,result):
    import cv2
    import pyrealsense2 as rs
    from calibration_core import object_points
    k=meta['depth_intrinsics']; intr=rs.intrinsics()
    for name in ['width','height','fx','fy','ppx','ppy']:setattr(intr,name,k[name])
    intr.model=getattr(rs.distortion,k['model'].split('.')[-1]); intr.coeffs=k['coeffs']
    ext=meta['depth_to_color']; R=np.array(ext['rotation']).reshape(3,3,order='F'); t=np.array(ext['translation_m'])
    K=np.array(result['camera_matrix']); distortion=np.array(result['distortion'])
    side=meta['square_mm']/1000; obj=object_points(side); output=[]
    for idx in result['heldout_indices']:
        v=meta['views'][idx]; raw=np.asarray(Image.open(session/v['depth']))
        ys,xs=np.mgrid[0:raw.shape[0]:4,0:raw.shape[1]:4]; z=raw[ys,xs]*meta['depth_scale_m']
        good=(z>0.15)&(z<5)
        points=np.array([rs.rs2_deproject_pixel_to_point(intr,[float(x),float(y)],float(d)) for x,y,d in zip(xs[good],ys[good],z[good])])
        if len(points)==0:output.append(dict(view=idx,status='NO_VALID_DEPTH'));continue
        pc=points@R.T+t
        ok,rv,tv=cv2.solvePnP(obj,np.array(v['corners'],np.float32),K,distortion)
        if not ok:output.append(dict(view=idx,status='POSE_FAILED'));continue
        board=(pc-tv.ravel())@cv2.Rodrigues(rv)[0]
        # Inner board area excludes boundary/background; zero depth remains absent.
        inside=(board[:,0]>0.5*side)&(board[:,0]<6.5*side)&(board[:,1]>0.5*side)&(board[:,1]<4.5*side)
        residual=board[inside,2]
        if len(residual)<30:output.append(dict(view=idx,status='INSUFFICIENT_DEPTH',samples=len(residual)));continue
        output.append(dict(view=idx,status='MEASURED_NOT_CERTIFIED',samples=len(residual),
                           signed_median_m=float(np.median(residual)),absolute_p95_m=float(np.percentile(abs(residual),95))))
    return dict(views=output,scope='Depth versus RGB-estimated target plane, dependent on measured square size and camera pose. Not independent absolute metrology; reflective screens may have invalid or biased depth.')

def imu_add(args):
    summary=json.loads((args.record/'summary.json').read_text())
    samples=json.loads((args.record/'samples.json').read_text())
    if summary['serial']!=args.serial:raise ValueError('IMU device serial mismatch')
    a=np.array([s['xyz'] for s in samples if s['stream']=='stream.accel'])
    g=np.array([s['xyz'] for s in samples if s['stream']=='stream.gyro'])
    if min(len(a),len(g))<100:raise ValueError('Too few samples')
    if not summary.get('timestamp_domains_consistent',False):raise ValueError('Timestamp domain transition: recapture')
    if max(a.std(axis=0))>0.08 or max(g.std(axis=0))>0.015 or np.linalg.norm(g.mean(axis=0))>0.03:
        raise ValueError('Motion/noise gate failed: hold camera stationary and recapture')
    axis='xyz'.index(args.pose[0]); sign=1 if args.pose[1]=='+' else -1
    direction=a.mean(axis=0)/np.linalg.norm(a.mean(axis=0))
    if sign*direction[axis]<np.cos(np.deg2rad(8)):raise ValueError('Wrong pose: named positive/negative specific-force axis must face UP/DOWN respectively')
    out=BASE/'imu_sets'/args.serial; out.mkdir(parents=True,exist_ok=True)
    path=out/f'{args.pose}.json'
    if path.exists():raise ValueError('Pose already recorded; preserve it or use another dataset directory')
    save(path,dict(pose=args.pose,serial=args.serial,source=str(args.record.resolve()),
                   accel_mean=a.mean(axis=0).tolist(),gyro_mean=g.mean(axis=0).tolist()))
    print(path)

def imu_solve(args):
    out=BASE/'imu_sets'/args.serial
    missing=[p for p in POSES if not (out/f'{p}.json').exists()]
    if missing:raise ValueError(f'Missing physical poses: {missing}')
    data=[json.loads((out/f'{p}.json').read_text()) for p in POSES]
    result=solve_imu({r['pose']:r['accel_mean'] for r in data},[r['gyro_mean'] for r in data])
    result['serial']=args.serial; save(out/'imu_candidate.json',result); print(json.dumps(result,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('target')
    c=sub.add_parser('capture'); c.add_argument('--seconds',type=float,default=45)
    c.add_argument('--square-mm',type=float,required=True,help='Measured physical square length, NOT assumed print size')
    c.add_argument('--serial',default=None)
    c.add_argument('--resume',type=Path,help='Copy accepted views into a new session; physical display size must be unchanged')
    s=sub.add_parser('solve'); s.add_argument('session',type=Path)
    a=sub.add_parser('imu-add'); a.add_argument('record',type=Path); a.add_argument('--pose',choices=POSES,required=True); a.add_argument('--serial',required=True)
    a=sub.add_parser('imu-solve'); a.add_argument('--serial',required=True)
    args=parser.parse_args()
    {'target':target,'capture':capture,'solve':solve,'imu-add':imu_add,'imu-solve':imu_solve}[args.command](args)

if __name__=='__main__':main()
