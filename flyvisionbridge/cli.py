"""Bounded RGB-only input, plus an offline synthetic walkthrough."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .bridge import Frame, map_frame, load_eye_mapping


def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo', action='store_true', help='Synthetic image; no camera opened')
    source.add_argument('--image', type=Path)
    source.add_argument('--camera', type=int, help='OpenCV camera index; captures one RGB frame')
    p.add_argument('--intrinsics', type=Path, help='JSON: fx,fy,ppx,ppy,width,height,coeffs; rectified image required')
    mapping=p.add_mutually_exclusive_group()
    mapping.add_argument('--mapping', type=Path)
    mapping.add_argument('--eyes',choices=['left','right','both'],default='right',help='Legacy snapshot default: right; live default: both')
    p.add_argument('--head-from-camera', type=Path, help='JSON proper rotation, 3x3, camera into head coordinates')
    p.add_argument('--depth', type=Path, help='Optional .npy color-camera Z in metres, matching RGB')
    p.add_argument('--output', type=Path, default=Path('outputs/rgb-snapshot'))
    args = p.parse_args()
    if not args.demo and args.intrinsics is None:
        p.error('--intrinsics is required; webcam focal lengths are not guessed')
    if args.output.exists():
        p.error('Output already exists; choose a new directory to preserve previous evidence')
    if args.demo:
        rgb = np.full((480,640,3),220,np.uint8);rgb[150:330,260:380]=30
        k = dict(fx=600.,fy=600.,ppx=319.5,ppy=239.5,width=640,height=480,coeffs=[0]*5)
        timestamp, clock = 0., 'SYNTHETIC'
    else:
        k = json.loads(args.intrinsics.read_text(encoding='utf8'))
        if args.image:
            rgb = np.asarray(Image.open(args.image).convert('RGB'))
            timestamp, clock = 0., 'STILL_IMAGE_TIME_UNKNOWN'
        else:
            import cv2
            cap = cv2.VideoCapture(args.camera)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,k['width']);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,k['height'])
                ok, bgr = cap.read()
                timestamp = time.monotonic();clock = 'HOST_RECEIPT_NOT_EXPOSURE'
                if not ok:raise RuntimeError('Camera did not return a frame')
                rgb = cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
            finally:
                cap.release()
    depth = np.load(args.depth,allow_pickle=False) if args.depth else None
    kwargs = {}
    if args.mapping:kwargs['mapping']=json.loads(args.mapping.read_text(encoding='utf8'))
    else:kwargs['mapping']=load_eye_mapping(args.eyes)
    if args.head_from_camera:kwargs['head_from_camera']=json.loads(args.head_from_camera.read_text(encoding='utf8'))
    result=map_frame(Frame(rgb,k,timestamp,clock,depth),**kwargs)
    result['source']='synthetic demonstration' if args.demo else ('still image' if args.image else 'OpenCV RGB camera')
    args.output.mkdir(parents=True)
    Image.fromarray(rgb).save(args.output/'rgb.png')
    (args.output/'intrinsics.json').write_text(json.dumps(k,indent=2),encoding='utf8')
    (args.output/'channels.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8')
    observed=sum(c['rgb_status']=='OBSERVED' for c in result['channels'])
    print(f"Saved {len(result['channels'])} channels; {observed} observed. No neural-response claim. {args.output}")


if __name__ == '__main__':main()
