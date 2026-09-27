"""Bounded-latency RGB capture. A reader drains frames; consumers take latest only."""
import subprocess
import threading
import time
import numpy as np


class LatestCamera:
    def __init__(self,width=640,height=480,fps=30,index=0,backend='auto',device_name=None,ffmpeg='ffmpeg'):
        self.size=(width,height);self.stop=threading.Event();self.condition=threading.Condition()
        self.latest=None;self.sequence=0;self.error=None;self.process=None;self.cap=None;self.stderr=[]
        if device_name:
            self.process=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-f','dshow',
                '-video_size',f'{width}x{height}','-framerate',str(fps),'-i','video='+device_name,
                '-an','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            def errors():
                for line in self.process.stderr:
                    self.stderr.append(line.decode('utf8',errors='replace').strip());self.stderr[:]=self.stderr[-10:]
            threading.Thread(target=errors,daemon=True).start()
        else:
            import cv2
            apis={'auto':cv2.CAP_ANY,'dshow':cv2.CAP_DSHOW,'msmf':cv2.CAP_MSMF,'v4l2':cv2.CAP_V4L2}
            self.cap=cv2.VideoCapture(index,apis[backend])
            if not self.cap.isOpened():self.cap.release();raise RuntimeError('Cannot open selected OpenCV camera')
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,width);self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,height)
            self.cap.set(cv2.CAP_PROP_FPS,fps);self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        self.thread=threading.Thread(target=self._read,daemon=True);self.thread.start()

    def _read(self):
        try:
            while not self.stop.is_set():
                if self.process:
                    needed=self.size[0]*self.size[1]*3;data=bytearray()
                    while len(data)<needed:
                        block=self.process.stdout.read(needed-len(data))
                        if not block:raise RuntimeError('Camera stream ended: '+'; '.join(self.stderr))
                        data.extend(block)
                    rgb=np.frombuffer(data,np.uint8).reshape(self.size[1],self.size[0],3).copy()
                else:
                    import cv2
                    ok,bgr=self.cap.read()
                    if not ok:raise RuntimeError('Camera read failed')
                    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                with self.condition:
                    self.sequence+=1;self.latest=(self.sequence,time.monotonic(),rgb);self.condition.notify_all()
        except Exception as exc:
            if not self.stop.is_set():self.error=str(exc)
            with self.condition:self.condition.notify_all()
        finally:
            if self.cap:self.cap.release()

    def frame(self,after=0,timeout=15.):
        end=time.monotonic()+timeout
        with self.condition:
            while self.latest is None or self.latest[0]<=after:
                if self.error:raise RuntimeError(self.error)
                remaining=end-time.monotonic()
                if remaining<=0:raise TimeoutError('No fresh camera frame')
                self.condition.wait(remaining)
            seq,stamp,rgb=self.latest
            return seq,stamp,rgb.copy()

    def close(self):
        self.stop.set()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Camera reader did not stop; close the capture process')
        if self.process:
            self.process.stdout.close();self.process.stderr.close()

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
