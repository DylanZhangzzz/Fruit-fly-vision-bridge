"""Webcam -> visual columns -> persistent whole-brain simulation -> local dashboard."""
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import numpy as np
from .bridge import Frame,map_frame,load_eye_mapping
from camera_lab.biomapping.geometry import ASSUMED_HEAD_FROM_CAMERA,rotation_checked
from .live_core import BrainClient,Rectifier,approximate_intrinsics,engineer_rates
from .live_camera import LatestCamera


class LiveApp:
    def __init__(self,args):
        self.args=args;self.lock=threading.RLock();self.stop=threading.Event()
        self.thread=None;self.control_requested=False;self.jpeg=None
        original=json.loads(args.intrinsics.read_text(encoding='utf8')) if args.intrinsics else approximate_intrinsics(args.width,args.height,args.assume_hfov)
        self.rectifier=Rectifier(original)
        self.rotation=rotation_checked(json.loads(args.head_from_camera.read_text(encoding='utf8')) if args.head_from_camera else ASSUMED_HEAD_FROM_CAMERA)
        self.width,self.height=original['width'],original['height']
        self.mapping=load_eye_mapping(args.eyes)
        self.brain=BrainClient(args.model_dir)
        self.state=dict(phase='idle',frames=0,brain=self.brain.ready,
            eyes=args.eyes,target_L2=len(self.mapping),targets_by_eye={eye:sum(r['eye']==eye for r in self.mapping) for eye in ['L','R']},
            camera=args.device_name or f'OpenCV camera {args.camera}',
            calibration=original.get('calibration_status','USER_SUPPLIED_INTRINSICS'),
            geometry=original,head_from_camera=self.rotation.tolist(),engineering_encoder='rate_hz = gain_hz * (1 - RGB code luminance)',
            gain_hz=args.gain_hz,model_step_ms=args.model_ms,target_updates_per_s=args.updates_per_second,
            biological_response_validated=False,history=[],depth='unavailable',imu='unavailable')

    def start(self,seconds=None):
        seconds=self.args.seconds if seconds is None else float(seconds)
        if not 2<=seconds<=600:raise ValueError('Capture duration must be 2..600 seconds')
        with self.lock:
            if self.thread and self.thread.is_alive():raise ValueError('A run is already active')
            self.stop.clear();self.control_requested=False
            self.jpeg=None
            self.state.update(phase='warming',frames=0,history=[],last=None,summary=None,error=None,controls=None,run_id=None,
                model_speed_ratio=None,updates_per_s=0,seconds=seconds)
            self.thread=threading.Thread(target=self._run,args=(seconds,),daemon=True);self.thread.start()

    def _controls(self,channels):
        result=self.brain.request('controls',channels=channels,steps=500)
        runs=result['runs']
        result['checks']=dict(no_input_silent=runs['no_input']['total_spikes']==0,
            camera_drives_input=runs['camera']['input_neuron_spikes']>0,
            camera_propagates=runs['camera']['downstream_spikes']>0,
            disconnected_downstream_silent=runs['connections_off']['downstream_spikes']==0,
            input_gain_changes_response=runs['half_gain']['total_spikes']!=runs['camera']['total_spikes'])
        result['scope']='Same captured RGB input; reset/seed-matched 50 ms model controls; engineering only'
        for eye,mode in [('L','left_only'),('R','right_only')]:
            selected=[c for c in channels if c.get('eye')==eye]
            if selected:
                result['checks'][f'{eye}_only_drives_input']=runs[mode]['input_neuron_spikes']>0
                result['checks'][f'{eye}_only_has_no_other_eye_drive']=runs[mode]['input_by_eye']['R' if eye=='L' else 'L']['channels']==0
        return result

    def _run(self,seconds):
        import cv2
        out=self.args.output/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        count=0;dropped=0;last_seq=0;sequence=[];ids=None
        begin=None;controls=None
        try:
            out.mkdir(parents=True,exist_ok=False)
            self.brain.request('reset')
            with LatestCamera(width=self.width,height=self.height,fps=self.args.camera_fps,index=self.args.camera,
                backend=self.args.backend,device_name=self.args.device_name,ffmpeg=self.args.ffmpeg) as camera:
                camera.frame();time.sleep(1.)
                begin=time.monotonic();deadline=begin+seconds;next_update=begin
                with (out/'frames.jsonl').open('w',encoding='utf8') as log:
                    while not self.stop.is_set() and time.monotonic()<deadline:
                        remaining=next_update-time.monotonic()
                        if remaining>0 and self.stop.wait(remaining):break
                        seq,stamp,rgb=camera.frame(after=last_seq)
                        if last_seq:dropped+=max(0,seq-last_seq-1)
                        last_seq=seq;rgb=self.rectifier.apply(rgb)
                        mapped=self.rectifier.mask_channels(map_frame(Frame(rgb,self.rectifier.k,stamp,'HOST_RECEIPT_NOT_EXPOSURE'),mapping=self.mapping,head_from_camera=self.rotation))
                        channels=engineer_rates(mapped,self.args.gain_hz)
                        if not channels:raise RuntimeError('No mapped L2 ray is visible; check camera intrinsics/mount')
                        ids=[c['bodyId'] for c in channels]
                        if count==0:
                            cv2.imwrite(str(out/'first_rgb.jpg'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                            (out/'first_input.json').write_text(json.dumps(channels,indent=2),encoding='utf8')
                            controls=self._controls(channels)
                            (out/'initial_controls.json').write_text(json.dumps(controls,indent=2),encoding='utf8')
                            with self.lock:self.state['controls']=controls
                            # Snapshot controls take model time; the next loop reads the latest frame.
                            begin=time.monotonic();deadline=begin+seconds;next_update=begin
                        with self.lock:
                            control_now=self.control_requested;self.control_requested=False
                        if control_now:
                            extra=self._controls(channels)
                            (out/f'controls_{count:05d}.json').write_text(json.dumps(extra,indent=2),encoding='utf8')
                            with self.lock:self.state['controls']=extra
                        response=self.brain.request('step',channels=channels,steps=round(self.args.model_ms/.1))
                        now=time.monotonic();count+=1
                        values=[c['rgb_code_luminance'] for c in mapped['channels'] if c['rgb_status']=='OBSERVED']
                        record=dict(frame=count,camera_sequence=seq,host_receipt_s=stamp,
                            wall_elapsed_s=now-begin,frame_age_ms=(now-stamp)*1000,
                            sampled_L2=len(channels),mean_luminance=float(np.mean(values)),
                            sampled_by_eye={eye:sum(c['eye']==eye for c in channels) for eye in ['L','R']},
                            mean_input_hz_by_eye={eye:float(np.mean([c['rate_hz'] for c in channels if c['eye']==eye])) if any(c['eye']==eye for c in channels) else None for eye in ['L','R']},
                            mean_input_hz=float(np.mean([c['rate_hz'] for c in channels])),
                            sampled_ids=ids,sampled_eyes=[c['eye'] for c in channels],rates_hz=[c['rate_hz'] for c in channels],
                            model_reset_for_controls=bool(count==1 or control_now),**response)
                        log.write(json.dumps(record,allow_nan=False)+'\n');log.flush();sequence.append(record)
                        preview=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
                        for c in mapped['channels']:
                            if c['rgb_status']=='OBSERVED':cv2.circle(preview,tuple(round(v) for v in c['pixel_uv']),2,(255,190,80) if c['eye']=='L' else (0,210,255),1)
                        ok,encoded=cv2.imencode('.jpg',preview,[cv2.IMWRITE_JPEG_QUALITY,80])
                        with self.lock:
                            if ok:self.jpeg=encoded.tobytes()
                            history=self.state['history']+[dict(t=record['wall_elapsed_s'],spikes=response['total_spikes'],rate=record['mean_input_hz'])]
                            self.state.update(phase='running',frames=count,last=record,history=history[-150:],
                                skipped_camera_frames=dropped,run_id=out.name,
                                updates_per_s=count/max(now-begin,.001),model_speed_ratio=count*response['model_ms']/1000/max(now-begin,.001))
                        # No unbounded queue or fictitious catch-up of unobserved frames.
                        next_update=max(next_update+1/self.args.updates_per_second,now)
        except Exception as exc:
            with self.lock:self.state.update(phase='error',error=str(exc))
        finally:
            summary=dict(run_id=out.name,frames=count,skipped_camera_frames=dropped,
                camera=self.state['camera'],geometry=self.rectifier.original,head_from_camera=self.rotation.tolist(),brain=self.brain.ready,
                encoder=self.state['engineering_encoder'],gain_hz=self.args.gain_hz,
                eyes=self.args.eyes,target_L2=len(self.mapping),targets_by_eye=self.state['targets_by_eye'],
                seconds_requested=seconds,model_ms_per_update=self.args.model_ms,
                biological_response_validated=False,raw_camera_data_public=False,
                initial_controls=controls,depth='UNAVAILABLE',imu='UNAVAILABLE',
                clock='HOST_RECEIPT_NOT_EXPOSURE',completed_utc=datetime.now(timezone.utc).isoformat())
            if sequence:
                total=sum(r['total_spikes'] for r in sequence)
                summary.update(sampled_L2=len(ids),sampled_ids=ids,total_spikes=total,
                    sampled_by_eye=sequence[-1]['sampled_by_eye'],
                    input_spikes_by_eye={eye:sum(r['input_by_eye'][eye]['spikes'] for r in sequence) for eye in ['L','R']},
                    downstream_spikes=sum(r['downstream_spikes'] for r in sequence),
                    model_ms_total=sum(r['model_ms'] for r in sequence),
                    wall_elapsed_s=sequence[-1]['wall_elapsed_s'],
                    observed_mean_luminance_range=[min(r['mean_luminance'] for r in sequence),max(r['mean_luminance'] for r in sequence)],
                    input_changed_between_frames=any(r['rates_hz']!=sequence[0]['rates_hz'] for r in sequence[1:]),
                    continuous_ticks=all(b['tick_before']==a['tick_after'] for a,b in zip(sequence,sequence[1:]) if not b['model_reset_for_controls']),
                    frame_age_ms_p50_p95=np.percentile([r['frame_age_ms'] for r in sequence],[50,95]).tolist())
            with self.lock:
                if self.state['phase']!='error':self.state['phase']='stopped'
                summary['error']=self.state.get('error');self.state['summary']=summary
            if out.is_dir():
                (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf8')
            print(json.dumps({'run':out.name,'frames':count,'error':summary['error']},ensure_ascii=False),flush=True)

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=30)
        self.brain.close()


def serve(app,port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,status=200,content_type='application/json'):
            data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8') if content_type=='application/json' else value
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        def do_GET(self):
            if self.headers.get('Host') not in [f'127.0.0.1:{port}',f'localhost:{port}']:
                return self.reply({'error':'Host rejected'},403)
            route=urlsplit(self.path).path
            if route=='/':return self.reply(Path(__file__).with_name('live_dashboard.html').read_bytes(),content_type='text/html; charset=utf-8')
            if route=='/api/state':
                with app.lock:return self.reply(app.state)
            if route=='/camera.jpg':
                with app.lock:data=app.jpeg
                if data:return self.reply(data,content_type='image/jpeg')
                return self.reply({'error':'No frame yet'},404)
            return self.reply({'error':'Not found'},404)
        def do_POST(self):
            if self.headers.get('Origin') not in [None,f'http://127.0.0.1:{port}',f'http://localhost:{port}']:
                return self.reply({'error':'Origin rejected'},403)
            if self.headers.get('Host') not in [f'127.0.0.1:{port}',f'localhost:{port}']:
                return self.reply({'error':'Host rejected'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=1024:raise ValueError('Request too large')
                data=json.loads(self.rfile.read(length) or '{}')
                if not isinstance(data,dict):raise ValueError('Expected a JSON object')
                if self.path=='/api/start':app.start(data.get('seconds'))
                elif self.path=='/api/stop':app.stop.set()
                elif self.path=='/api/shutdown':
                    app.stop.set();threading.Thread(target=server.shutdown,daemon=True).start()
                elif self.path=='/api/controls':
                    with app.lock:
                        if app.state['phase']!='running':raise ValueError('Start a live run first')
                        app.control_requested=True
                else:return self.reply({'error':'Not found'},404)
                self.reply({'ok':True})
            except (ValueError,TypeError) as exc:self.reply({'error':str(exc)},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Webcam brain dashboard: http://127.0.0.1:{port}/',flush=True)
    try:server.serve_forever()
    finally:server.server_close();app.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir',type=Path,default=Path(os.environ.get('FLYVISION_MODEL_DIR','fruit-fly-simulation')))
    p.add_argument('--camera',type=int,default=0)
    p.add_argument('--eyes',choices=['left','right','both'],default='both',help='Drive published left/right mappings; live default is both')
    p.add_argument('--backend',choices=['auto','dshow','msmf','v4l2'],default='auto')
    p.add_argument('--device-name',help='Windows DirectShow camera name; uses installed FFmpeg')
    p.add_argument('--ffmpeg',default='ffmpeg')
    geometry=p.add_mutually_exclusive_group(required=True)
    geometry.add_argument('--intrinsics',type=Path)
    geometry.add_argument('--assume-hfov',type=float,help='Explicit approximate horizontal FOV; NOT a calibration')
    p.add_argument('--head-from-camera',type=Path,help='JSON proper rotation from camera into head coordinates')
    p.add_argument('--width',type=int,default=640);p.add_argument('--height',type=int,default=480)
    p.add_argument('--camera-fps',type=int,default=30)
    p.add_argument('--updates-per-second',type=float,default=5.)
    p.add_argument('--model-ms',type=float,default=20.)
    p.add_argument('--gain-hz',type=float,default=120.)
    p.add_argument('--seconds',type=float,default=60.)
    p.add_argument('--output',type=Path,default=Path('outputs/webcam-live'))
    p.add_argument('--port',type=int,default=8771)
    p.add_argument('--start',action='store_true',help='Start one bounded run when server launches')
    args=p.parse_args()
    if not 1<=args.updates_per_second<=30 or not .1<=args.model_ms<=100 or not 2<=args.seconds<=600 or not 0<=args.gain_hz<=120:
        p.error('Invalid update rate, model duration, capture duration or gain')
    if args.width<2 or args.height<2 or not 1<=args.camera_fps<=120:
        p.error('Invalid image dimensions or camera frame rate')
    args.model_ms=round(args.model_ms/.1)*.1
    if not (args.model_dir/'src/brain.js').is_file():p.error('Pass the separate fruit-fly-simulation directory via --model-dir')
    app=LiveApp(args)
    try:
        if args.start:app.start()
        serve(app,args.port)
    finally:app.close()


if __name__=='__main__':main()
