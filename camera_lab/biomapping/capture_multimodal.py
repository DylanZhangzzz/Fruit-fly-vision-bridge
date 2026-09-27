"""Bounded RGB/depth/IMU recording with timestamps; no device calibration writes."""
import json
import time
import sys
from pathlib import Path
from datetime import datetime
import numpy as np
from PIL import Image
import pyrealsense2 as rs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from probe_camera import intrinsics
from device_selection import select_serial

def main():
    out=Path(__file__).resolve().parent/'captures'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    serial=select_serial();pipe=rs.pipeline();cfg=rs.config();cfg.enable_device(serial)
    cfg.enable_stream(rs.stream.color,640,480,rs.format.rgb8,30)
    cfg.enable_stream(rs.stream.depth,640,480,rs.format.z16,30)
    cfg.enable_stream(rs.stream.accel,rs.format.motion_xyz32f,63)
    cfg.enable_stream(rs.stream.gyro,rs.format.motion_xyz32f,200)
    motion=[];video=[];errors=[];started=time.monotonic();last_time=[0.]
    def callback(frame):
        try:
            host_ms=time.monotonic()*1000
            if time.monotonic()-started<2:return
            if frame.is_motion_frame():
                f=frame.as_motion_frame();v=f.get_motion_data()
                motion.append(dict(stream=str(f.profile.stream_type()),timestamp_ms=f.get_timestamp(),
                                   domain=str(f.get_frame_timestamp_domain()),host_receipt_ms=host_ms,xyz=[v.x,v.y,v.z]))
            elif frame.is_frameset() and time.monotonic()-last_time[0]>=0.2:
                fs=frame.as_frameset();c=fs.get_color_frame();d=fs.get_depth_frame()
                if c and d:
                    video.append(dict(rgb=np.asanyarray(c.get_data()).copy(),depth=np.asanyarray(d.get_data()).copy(),
                                      color_ms=c.get_timestamp(),depth_ms=d.get_timestamp(),
                                      host_receipt_ms=host_ms,
                                      color_clock=str(c.get_frame_timestamp_domain()),depth_clock=str(d.get_frame_timestamp_domain())))
                    last_time[0]=time.monotonic()
        except Exception as e:errors.append(str(e))
    profile=pipe.start(cfg,callback)
    try:
        color=profile.get_stream(rs.stream.color);depth=profile.get_stream(rs.stream.depth)
        ext=depth.get_extrinsics_to(color)
        report=dict(serial=serial,color_intrinsics=intrinsics(color),depth_intrinsics=intrinsics(depth),
                    depth_scale_m=profile.get_device().first_depth_sensor().get_depth_scale(),
                    depth_to_color=dict(rotation=ext.rotation,translation_m=ext.translation),imu_extrinsics={})
        for name,stream in [('accel',rs.stream.accel),('gyro',rs.stream.gyro)]:
            e=profile.get_stream(stream).get_extrinsics_to(color)
            report['imu_extrinsics'][name]=dict(rotation=e.rotation,translation_m=e.translation)
        time.sleep(7)
    finally:pipe.stop()
    if errors:raise RuntimeError(errors[:3])
    if not video or not motion:raise RuntimeError(f'Missing modality: video={len(video)}, IMU={len(motion)}')
    timings=[]
    for i,v in enumerate(video):
        Image.fromarray(v['rgb']).save(out/f'rgb_{i:03d}.png');Image.fromarray(v['depth']).save(out/f'depth_{i:03d}.png')
        timings.append({k:value for k,value in v.items() if k not in ['rgb','depth']})
    Image.fromarray(video[-1]['rgb']).save(out/'rgb.png');Image.fromarray(video[-1]['depth']).save(out/'depth_raw_u16.png')
    report['frames_timing']=timings;report['imu_samples']=len(motion)
    (out/'report.json').write_text(json.dumps(report,indent=2));(out/'imu.json').write_text(json.dumps(motion))
    print(json.dumps(dict(capture=str(out),video_frames=len(video),imu_samples=len(motion))))

if __name__=='__main__':main()
