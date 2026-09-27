"""Read-only bounded D435i IMU probe. Does not write device calibration.

Collect while stationary for a useful gravity/bias diagnostic. A single pose
cannot calibrate scale, all biases, absolute yaw, or biological eye direction.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
import numpy as np
import pyrealsense2 as rs

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,default=5)
    p.add_argument('--serial',default=None)
    args=p.parse_args()
    from device_selection import select_serial
    args.serial=select_serial(args.serial)
    if not 1<=args.seconds<=30:raise ValueError('Use 1..30 seconds')
    out=Path(__file__).resolve().parent/'imu'/datetime.now().strftime('%Y%m%d-%H%M%S')
    out.mkdir(parents=True,exist_ok=True)
    pipe=rs.pipeline(); cfg=rs.config(); cfg.enable_device(args.serial)
    cfg.enable_stream(rs.stream.color,640,480,rs.format.rgb8,30)
    cfg.enable_stream(rs.stream.accel,rs.format.motion_xyz32f,63)
    cfg.enable_stream(rs.stream.gyro,rs.format.motion_xyz32f,200)
    rows=[]
    def on_frame(frame):
        if frame.is_motion_frame():
            f=frame.as_motion_frame(); d=f.get_motion_data()
            rows.append(dict(stream=str(f.profile.stream_type()),timestamp_ms=f.get_timestamp(),
                             domain=str(f.get_frame_timestamp_domain()),xyz=[d.x,d.y,d.z]))
    profile=pipe.start(cfg,on_frame)
    try:
        color=profile.get_stream(rs.stream.color)
        accel=profile.get_stream(rs.stream.accel); ext=accel.get_extrinsics_to(color)
        motion_calibration={}
        for stream in [rs.stream.accel,rs.stream.gyro]:
            s=profile.get_stream(stream).as_motion_stream_profile(); intr=s.get_motion_intrinsics()
            motion_calibration[str(stream)]={'data':intr.data,'noise_variances':intr.noise_variances,'bias_variances':intr.bias_variances}
        # Exclude startup transients and the initial timestamp-domain transition.
        time.sleep(2)
        rows.clear()
        time.sleep(args.seconds)
    finally:pipe.stop()
    (out/'samples.json').write_text(json.dumps(rows),encoding='utf-8')
    stats={}
    for name in ['accel','gyro']:
        subset=[r for r in rows if r['stream']==f'stream.{name}']
        a=np.array([r['xyz'] for r in subset])
        if len(a)<10:raise RuntimeError(f'Too few {name} samples; raw data saved')
        stats[name]=dict(samples=len(a),mean=a.mean(axis=0).tolist(),std=a.std(axis=0).tolist(),
                         timestamp_domains=sorted(set(r['domain'] for r in subset)))
    r=np.array(ext.rotation).reshape(3,3,order='F')
    specific_force=r@np.array(stats['accel']['mean'])
    summary=dict(serial=args.serial,duration_s=args.seconds,warmup_s=2,stats=stats,
        units={'accel':'m/s^2','gyro':'rad/s'},accel_to_color_rotation_column_major=ext.rotation,
        accel_to_color_translation_m=ext.translation,reported_motion_intrinsics=motion_calibration,
        mean_specific_force_color_xyz=specific_force.tolist(),
        mean_accel_norm_m_s2=float(np.linalg.norm(specific_force)),
        gravity_direction_color_if_stationary=(-specific_force/np.linalg.norm(specific_force)).tolist(),
        scope='Read-only diagnostic, no stationarity guarantee. Gravity is negative specific force only when stationary.',
        absolute_yaw='UNOBSERVABLE_FROM_GRAVITY',biological_eye_alignment='UNVERIFIED',
        timestamp_domains_consistent=len(set(r['domain'] for r in rows))==1,
        motion_intrinsics_note='Identity/zero SDK values do not establish that this device is calibrated.',
        calibration_written=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2)); print(out)

if __name__=='__main__':main()
