"""Explicit engineering encoding, rectification, and a persistent brain client."""
import json
import math
from pathlib import Path
import queue
import subprocess
import threading
import numpy as np


def approximate_intrinsics(width,height,hfov_deg):
    if width<2 or height<2 or not 10<=hfov_deg<=160:
        raise ValueError('Need positive image dimensions and assumed horizontal FOV 10..160 degrees')
    focal=width/(2*math.tan(math.radians(hfov_deg)/2))
    return dict(width=width,height=height,fx=focal,fy=focal,ppx=(width-1)/2,ppy=(height-1)/2,
        coeffs=[0]*5,calibration_status='APPROXIMATE_FOV_NOT_CALIBRATED',assumed_hfov_deg=hfov_deg)


def engineer_rates(mapped,gain_hz=120.):
    if not np.isfinite(gain_hz) or not 0<=gain_hz<=120:raise ValueError('gain_hz must be 0..120')
    result=[]
    for c in mapped['channels']:
        if c['rgb_status']!='OBSERVED':continue
        lum=c['rgb_code_luminance']
        if lum is None or not np.isfinite(lum) or not 0<=lum<=1+1e-12:
            raise ValueError('Observed RGB luminance must be finite and in 0..1')
        result.append(dict(bodyId=c['bodyId'],rate_hz=float(gain_hz*(1-min(lum,1.)))))
    return result


class Rectifier:
    """Standard OpenCV Brown/rational intrinsics; preserve invalid border pixels."""
    def __init__(self,intrinsics):
        import cv2
        self.original=dict(intrinsics);self.k=dict(intrinsics)
        if any(not isinstance(self.k[k],int) or self.k[k]<2 for k in ['width','height']):
            raise ValueError('Intrinsics dimensions must be integers >= 2')
        if not np.isfinite([self.k[k] for k in ['fx','fy','ppx','ppy']]).all() or min(self.k['fx'],self.k['fy'])<=0:
            raise ValueError('Intrinsics must be finite with positive focal lengths')
        self.maps=None;self.valid=np.ones((self.k['height'],self.k['width']),bool)
        coeffs=np.asarray(self.k.get('coeffs',[0]*5),float)
        if not np.isfinite(coeffs).all():raise ValueError('Nonfinite distortion')
        if np.any(coeffs):
            if self.k.get('model','opencv') not in ['opencv','brown_conrady','distortion.brown_conrady']:
                raise ValueError('Use standard OpenCV distortion coefficients, not a fisheye/inverse model')
            K=np.array([[self.k['fx'],0,self.k['ppx']],[0,self.k['fy'],self.k['ppy']],[0,0,1]],float)
            size=(self.k['width'],self.k['height'])
            self.maps=cv2.initUndistortRectifyMap(K,coeffs,None,K,size,cv2.CV_32FC1)
            x,y=self.maps
            self.valid=(x>=0)&(y>=0)&(x<self.k['width']-1)&(y<self.k['height']-1)
        self.k['coeffs']=[0]*5

    def apply(self,rgb):
        import cv2
        if rgb.shape[:2]!=(self.k['height'],self.k['width']):raise ValueError('Actual camera resolution differs from intrinsics')
        return cv2.remap(rgb,*self.maps,cv2.INTER_LINEAR) if self.maps is not None else rgb

    def mask_channels(self,mapped):
        # A bilinear sample is valid only if all four rectified pixels are valid.
        for c in mapped['channels']:
            if c['rgb_status']!='OBSERVED':continue
            x,y=(int(v) for v in c['pixel_uv'])
            if not self.valid[y:y+2,x:x+2].all():
                c.update(rgb_status='INVALID_RECTIFICATION_BORDER',rgb_code_luminance=None,depth_color_z_m=None)
        return mapped


class BrainClient:
    def __init__(self,model_dir,timeout=60.):
        self.timeout=timeout;self.next_id=0;self.responses=queue.Queue()
        self.lock=threading.Lock();self.stderr=[]
        self.proc=subprocess.Popen(['node',str(Path(__file__).with_name('brain_worker.mjs')),str(model_dir)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',bufsize=1)
        def reader():
            try:
                for line in self.proc.stdout:self.responses.put(json.loads(line))
            except Exception as exc:self.responses.put({'event':'invalid','error':str(exc)})
            finally:self.responses.put({'event':'eof'})
        def errors():
            for line in self.proc.stderr:self.stderr.append(line.strip());self.stderr[:]=self.stderr[-12:]
        threading.Thread(target=reader,daemon=True).start();threading.Thread(target=errors,daemon=True).start()
        try:
            self.ready=self._receive()
            if self.ready.get('event')!='ready':raise RuntimeError('Brain did not start: '+'; '.join(self.stderr))
        except Exception:
            self.close();raise

    def _receive(self):
        try:return self.responses.get(timeout=self.timeout)
        except queue.Empty:
            self.close();raise TimeoutError('Brain response timed out')

    def request(self,command,**kwargs):
        with self.lock:
            self.next_id+=1
            self.proc.stdin.write(json.dumps(dict(id=self.next_id,command=command,**kwargs),allow_nan=False)+'\n');self.proc.stdin.flush()
            result=self._receive()
            if result.get('id')!=self.next_id:raise RuntimeError('Brain worker terminated or returned mismatched response: '+'; '.join(self.stderr))
            if not result.get('ok'):raise ValueError(result.get('error','Brain request failed'))
            return result

    def close(self):
        if getattr(self,'proc',None) is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=5)
            for pipe in [self.proc.stdin,self.proc.stdout,self.proc.stderr]:
                if pipe:pipe.close()

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
