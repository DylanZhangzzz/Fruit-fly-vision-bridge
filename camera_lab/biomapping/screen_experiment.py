"""Local, bounded screen -> D435i acquisition. Run and stop via localhost UI.

Every unique RGB frame is retained in lossless FFV1, depth at 1 Hz, IMU at
native rate. Camera options are restored on exit. No camera upload.
"""
import json
import hashlib
import queue
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import sys
import cv2
import numpy as np
import pyrealsense2 as rs

BASE=Path(__file__).resolve().parent
ROOT=BASE/'screen_experiment'
ROOT.mkdir(exist_ok=True)
sys.path.insert(0,str(BASE.parent))
from probe_camera import intrinsics
from device_selection import select_serial

STATE={'phase':'idle','ready':False,'frames':0}
LOCK=threading.Lock()
STOP=threading.Event()


def preview_coverage(out,meta):
    """Show actual author-mapped rays, without changing camera/head alignment."""
    from analyze_screen import screen_transform
    from geometry import project_rays
    from import_author_map import STATUS
    rows=[r for r in json.loads((BASE/'data/malecns_author_crosswalk.json').read_text()) if r['status']==STATUS]
    uv,visible=project_rays([r['ray_head_xyz'] for r in rows],meta['color_intrinsics'])
    uv=uv[visible];ids=[r['bodyId'] for r,v in zip(rows,visible) if v]
    cap=cv2.VideoCapture(str(out/'rgb.avi'));cap.set(cv2.CAP_PROP_POS_FRAMES,60);ok,frame=cap.read();cap.release()
    if not ok:return {'mapped_L2':0,'error':'Preview frame unavailable'}
    H,n=screen_transform(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY));inside=np.zeros(len(ids),bool)
    if H is not None:
        xy=cv2.perspectiveTransform(uv.astype(np.float32)[None],H)[0]
        inside=(xy[:,0]>225)&(xy[:,0]<775)&(xy[:,1]>205)&(xy[:,1]<495)
    for (x,y),hit in zip(uv,inside):cv2.circle(frame,(round(x),round(y)),4,(0,220,0) if hit else (0,170,255),1)
    cv2.putText(frame,f'Screen L2: {sum(inside)} | markers: {n}',(10,465),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,0),1)
    cv2.imwrite(str(out/'coverage.jpg'),frame)
    return dict(mapped_L2=int(sum(inside)),bodyIds=np.array(ids)[inside].tolist(),markers=n,image=f'/runs/{out.name}/coverage.jpg')


def acquire(preview=False,protocol='temporal',calibration=None,stimulus_page=None,reference_correction=None):
    global STATE
    out=ROOT/'runs'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    if stimulus_page:(out/'stimulus_snapshot.html').write_bytes((ROOT/stimulus_page).read_bytes())
    if protocol=='calibrated_temporal_v1':
        source=ROOT/'runs'/calibration/'response_lut.json'
        (out/'frozen_response_lut.json').write_bytes(source.read_bytes())
        if not stimulus_page:(out/'stimulus_snapshot.html').write_bytes((ROOT/'calibrated_temporal.html').read_bytes())
    STATE.update(phase='warming',ready=False,frames=0,output=str(out),error=None)
    serial=select_serial();pipe=rs.pipeline();cfg=rs.config();cfg.enable_device(serial)
    cfg.enable_stream(rs.stream.color,640,480,rs.format.rgb8,60)
    cfg.enable_stream(rs.stream.depth,640,480,rs.format.z16,30)
    cfg.enable_stream(rs.stream.gyro,rs.format.motion_xyz32f,200)
    cfg.enable_stream(rs.stream.accel,rs.format.motion_xyz32f,63)
    q=queue.Queue(maxsize=240);motion=[];errors=[];dropped=[0];active=[False]
    writer=None;profile=None;saved=[];records=[];last_rgb=-1;last_depth=-1;depth_saved=0
    def callback(f):
        host=time.monotonic()*1000
        try:
            if f.is_motion_frame():
                if active[0]:
                    m=f.as_motion_frame();v=m.get_motion_data()
                    motion.append(dict(stream=str(f.profile.stream_type()),timestamp_ms=f.get_timestamp(),
                        domain=str(f.get_frame_timestamp_domain()),host_receipt_ms=host,xyz=[v.x,v.y,v.z]))
            elif f.is_frameset():
                # Retain SDK frame ownership through the queue.
                f.keep()
                try:q.put_nowait((f,host))
                except queue.Full:dropped[0]+=1
        except Exception as e:errors.append(str(e))
    try:
        profile=pipe.start(cfg,callback)
        color=profile.get_stream(rs.stream.color);depth=profile.get_stream(rs.stream.depth)
        sensor=profile.get_device().first_color_sensor()
        option_names=['enable_auto_exposure','enable_auto_white_balance','exposure','gain','white_balance',
                      'brightness','contrast','gamma','hue','saturation','sharpness','backlight_compensation','power_line_frequency']
        options=[getattr(rs.option,name) for name in option_names if hasattr(rs.option,name) and sensor.supports(getattr(rs.option,name))]
        for option in options:
            if sensor.supports(option):saved.append((sensor,option,sensor.get_option(option)))
        started=time.monotonic()
        # Warm white balance, then hold both exposure and color gain fixed.
        while time.monotonic()-started<1.5:
            try:q.get(timeout=.2)
            except queue.Empty:pass
        sensor.set_option(rs.option.enable_auto_exposure,0)
        sensor.set_option(rs.option.exposure,80)
        sensor.set_option(rs.option.gain,64)
        sensor.set_option(rs.option.enable_auto_white_balance,0)
        if protocol=='calibrated_temporal_v1':
            fixed=json.loads((out/'frozen_response_lut.json').read_text())['capture_settings']
            for option in options:
                if str(option) in fixed:sensor.set_option(option,fixed[str(option)])
        while not q.empty():q.get_nowait()
        ext=depth.get_extrinsics_to(color)
        meta=dict(serial=serial,protocol=protocol,stimulus_page=stimulus_page,reference_correction=reference_correction,requested_rgb_fps=60,color_intrinsics=intrinsics(color),
                  depth_intrinsics=intrinsics(depth),depth_scale_m=profile.get_device().first_depth_sensor().get_depth_scale(),
                  depth_to_color=dict(rotation=ext.rotation,translation_m=ext.translation),
                  exposure_settings={str(o):sensor.get_option(o) for o in options},
                  exposure_units='SDK color exposure units; actual frame metadata retained where supported',
                  imu_extrinsics={})
        if calibration:
            meta.update(calibration_run=calibration,frozen_lut_sha256=hashlib.sha256((out/'frozen_response_lut.json').read_bytes()).hexdigest())
        for name,stream in [('accel',rs.stream.accel),('gyro',rs.stream.gyro)]:
            e=profile.get_stream(stream).get_extrinsics_to(color)
            meta['imu_extrinsics'][name]=dict(rotation=e.rotation,translation_m=e.translation)
        writer=cv2.VideoWriter(str(out/'rgb.avi'),cv2.VideoWriter_fourcc(*'FFV1'),60,(640,480))
        if not writer.isOpened():raise RuntimeError('Lossless video writer unavailable')
        recording=time.monotonic();active[0]=True
        STATE.update(phase='recording',ready=True)
        deadline=recording+(3 if preview else 45)
        while time.monotonic()<deadline and not STOP.is_set():
            try:f,host=q.get(timeout=1)
            except queue.Empty:continue
            fs=f.as_frameset();c=fs.get_color_frame();d=fs.get_depth_frame()
            if c and c.get_frame_number()!=last_rgb:
                last_rgb=c.get_frame_number();rgb=np.asanyarray(c.get_data()).copy()
                writer.write(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                record=dict(frame_index=len(records),color_frame_number=last_rgb,color_ms=c.get_timestamp(),
                            color_clock=str(c.get_frame_timestamp_domain()),host_receipt_ms=host)
                for name in ['actual_exposure','gain_level','frame_timestamp','sensor_timestamp']:
                    key=getattr(rs.frame_metadata_value,name,None)
                    if key is not None and c.supports_frame_metadata(key):record[name]=c.get_frame_metadata(key)
                records.append(record);STATE['frames']=len(records)
                if len(records)%15==1:
                    _,buf=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                    # Atomic replacement prevents partial preview reads.
                    tmp=ROOT/'preview.tmp';tmp.write_bytes(buf.tobytes());tmp.replace(ROOT/'preview.jpg')
                    if len(records)==1:cv2.imwrite(str(out/'first_rgb.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            if d and d.get_frame_number()!=last_depth and time.monotonic()-recording>=depth_saved:
                last_depth=d.get_frame_number();a=np.asanyarray(d.get_data())
                cv2.imwrite(str(out/f'depth_{depth_saved:03d}.png'),a)
                meta.setdefault('depth_frames',[]).append(dict(file=f'depth_{depth_saved:03d}.png',
                    timestamp_ms=d.get_timestamp(),domain=str(d.get_frame_timestamp_domain()),host_receipt_ms=host))
                depth_saved+=1
        active[0]=False
        meta.update(frames_timing=records,imu_samples=len(motion),queue_drops=dropped[0],callback_errors=errors,
                    capture_wall_s=time.monotonic()-recording,preview_only=preview)
        (out/'capture.json').write_text(json.dumps(meta,indent=2))
        (out/'imu.json').write_text(json.dumps(motion))
        STATE.update(phase='preview_processing' if preview else 'captured',ready=False)
    except Exception as e:
        STATE.update(phase='error',ready=False,error=str(e))
        (out/'error.json').write_text(json.dumps(dict(error=str(e))))
    finally:
        if writer is not None:writer.release()
        # Manual values restored first, then original auto modes.
        restore_errors=[]
        for sensor,option,value in reversed(saved):
            try:sensor.set_option(option,value)
            except Exception as e:restore_errors.append(str(e))
        if profile is not None:pipe.stop()
        STATE['restore_errors']=restore_errors
    if STATE['phase']=='preview_processing':
        try:STATE.update(phase='preview_done',preview=preview_coverage(out,meta))
        except Exception as e:STATE.update(phase='error',error=str(e))
    if STATE['phase']=='captured':
        STATE['phase']='analyzing'
        try:
            if protocol=='photometric':
                from analyze_photometric import analyze
            elif protocol=='calibrated_temporal_v1':
                from analyze_calibrated import analyze
            else:
                from analyze_screen import analyze
            result=analyze(out)
            STATE.update(phase='done',result=result,result_url=f'/runs/{out.name}/index.html')
        except Exception as e:STATE.update(phase='analysis_error',error=str(e))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def log_message(self,*a):pass
    def json_reply(self,obj,status=200):
        b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=='/api/status':return self.json_reply(STATE)
        if self.path.startswith('/marker/'):
            try:i=int(self.path.split('/')[-1].split('.')[0]);assert 0<=i<4
            except Exception:return self.send_error(400)
            im=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),i,140)
            _,buf=cv2.imencode('.png',im);b=buf.tobytes();self.send_response(200)
            self.send_header('Content-Type','image/png');self.end_headers();self.wfile.write(b);return
        return super().do_GET()
    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and origin!='http://127.0.0.1:8769':return self.send_error(403)
        length=int(self.headers.get('Content-Length',0))
        if length>2000000:return self.send_error(413)
        data=json.loads(self.rfile.read(length) or b'{}')
        if self.path in ['/api/run','/api/preview']:
            protocol=data.get('protocol','temporal')
            stimulus_page=data.get('stimulus_page')
            reference_correction=data.get('reference_correction')
            if reference_correction not in [None,'dual_patch_affine_v1']:return self.json_reply({'error':'unknown reference correction'},400)
            if stimulus_page not in [None,'continuous_validation.html']:return self.json_reply({'error':'unknown stimulus page'},400)
            if protocol not in ['temporal','photometric','calibrated_temporal_v1']:return self.json_reply({'error':'unknown protocol'},400)
            calibration=None
            if protocol=='calibrated_temporal_v1':
                calibration=data.get('calibration','')
                # Only existing, locally validated response tables can be frozen.
                if not calibration or any(c not in '0123456789-' for c in calibration):return self.json_reply({'error':'invalid calibration run'},400)
                source=ROOT/'runs'/calibration
                try:
                    accepted=json.loads((source/'photometric_report.json').read_text())['status']=='PASS'
                    assert accepted and (source/'response_lut.json').is_file()
                except Exception:return self.json_reply({'error':'calibration has not passed'},400)
            with LOCK:
                if STATE['phase'] in ['warming','recording','captured','analyzing','preview_processing']:return self.json_reply({'error':'busy'},409)
                STOP.clear();STATE.update(phase='warming',ready=False,error=None)
                threading.Thread(target=acquire,args=(self.path.endswith('preview'),protocol,calibration,stimulus_page,reference_correction),daemon=True).start()
            return self.json_reply({'started':True})
        if self.path=='/api/finish':
            if STATE['phase']!='recording':return self.json_reply({'error':'not recording'},409)
            (Path(STATE['output'])/'display_log.json').write_text(json.dumps(data))
            STOP.set();return self.json_reply({'saved':True})
        return self.send_error(404)


if __name__=='__main__':
    print('Screen experiment: http://127.0.0.1:8769/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8769),Handler).serve_forever()
