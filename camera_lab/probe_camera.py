"""Bounded RealSense RGB-D probe. Saves locally, always releases the camera."""
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyrealsense2 as rs
from PIL import Image


def intrinsics(profile):
    i = profile.as_video_stream_profile().get_intrinsics()
    return dict(width=i.width, height=i.height, fx=i.fx, fy=i.fy,
                ppx=i.ppx, ppy=i.ppy, model=str(i.model), coeffs=i.coeffs)


def main():
    devices = list(rs.context().query_devices())
    if not devices:
        raise RuntimeError('No RealSense camera detected')
    device = devices[0]
    report = {'device_count': len(devices), 'device': {}}
    for key in ['name', 'serial_number', 'firmware_version', 'usb_type_descriptor']:
        field = getattr(rs.camera_info, key)
        report['device'][key] = device.get_info(field) if device.supports(field) else None
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(report['device']['serial_number'])
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
    profile = pipeline.start(config)
    try:
        scale = profile.get_device().first_depth_sensor().get_depth_scale()
        align = rs.align(rs.stream.color)
        for _ in range(30):
            pipeline.wait_for_frames(5000)
        records = []
        started = time.perf_counter()
        for _ in range(90):
            frames = pipeline.wait_for_frames(5000)
            depth, color = frames.get_depth_frame(), frames.get_color_frame()
            if not depth or not color:
                raise RuntimeError('Incomplete RGB-D frameset')
            records.append({'depth_number': depth.get_frame_number(),
                            'color_number': color.get_frame_number(),
                            'depth_ms': depth.get_timestamp(),
                            'color_ms': color.get_timestamp(),
                            'depth_clock': str(depth.get_frame_timestamp_domain()),
                            'color_clock': str(color.get_frame_timestamp_domain())})
        elapsed = time.perf_counter() - started
        raw_depth = np.asanyarray(depth.get_data()).copy()
        rgb = np.asanyarray(color.get_data()).copy()
        aligned = align.process(frames).get_depth_frame()
        aligned_depth = np.asanyarray(aligned.get_data()).copy()
        report.update(depth_scale_m=scale, requested_fps=30, frames=len(records),
                      elapsed_s=elapsed, framesets_per_second=len(records)/elapsed,
                      unique_color_frames=len({r['color_number'] for r in records}),
                      unique_depth_frames=len({r['depth_number'] for r in records}),
                      depth_intrinsics=intrinsics(depth.profile),
                      color_intrinsics=intrinsics(color.profile),
                      aligned_depth_intrinsics=intrinsics(aligned.profile),
                      raw_depth_valid_fraction=float(np.mean(raw_depth > 0)),
                      aligned_depth_valid_fraction=float(np.mean(aligned_depth > 0)))
        extr = depth.profile.get_extrinsics_to(color.profile)
        report['depth_to_color'] = dict(rotation=extr.rotation, translation_m=extr.translation)
        valid = aligned_depth[aligned_depth > 0] * scale
        report['aligned_depth_percentiles_m'] = np.percentile(valid, [5, 50, 95]).tolist() if valid.size else []
        report['frames_timing'] = records
    finally:
        pipeline.stop()
    output = Path(__file__).parent / 'captures' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    Image.fromarray(rgb).save(output / 'rgb.png')
    Image.fromarray(raw_depth).save(output / 'depth_raw_u16.png')
    Image.fromarray(aligned_depth).save(output / 'depth_aligned_u16.png')
    meters = aligned_depth.astype(np.float32) * scale
    grey = (np.clip(meters / 3, 0, 1) * 255).astype(np.uint8)
    visual = np.stack([grey, 255-grey, np.full_like(grey, 128)], axis=-1)
    visual[aligned_depth == 0] = 0
    Image.fromarray(np.concatenate([rgb, visual], axis=1)).save(output / 'preview.png')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary = {k: v for k, v in report.items() if k not in
               ['frames_timing', 'depth_intrinsics', 'color_intrinsics', 'aligned_depth_intrinsics', 'depth_to_color']}
    summary['output'] = str(output.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
