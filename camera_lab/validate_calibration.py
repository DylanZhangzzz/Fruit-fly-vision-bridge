import os
from pathlib import Path
"""Independent SDK/NumPy geometry and recorded RGB-D alignment audit."""
import json
from pathlib import Path
import numpy as np
import pyrealsense2 as rs
from PIL import Image
from encode_depth import ROOT

CAP=Path(os.environ.get('FLYVISION_LEGACY_CAPTURE', str(ROOT/'camera_lab/captures/legacy')))
OUT=ROOT/'camera_lab/validation'

def intr(d):
    i=rs.intrinsics()
    for k in ['width','height','fx','fy','ppx','ppy']:setattr(i,k,d[k])
    i.coeffs=d['coeffs'];i.model=getattr(rs.distortion,d['model'].split('.')[-1])
    return i

def main():
    r=json.loads((CAP/'report.json').read_text())
    di,ci=intr(r['depth_intrinsics']),intr(r['color_intrinsics'])
    ext=rs.extrinsics();ext.rotation=r['depth_to_color']['rotation'];ext.translation=r['depth_to_color']['translation_m']
    rotation=np.array(ext.rotation).reshape(3,3,order='F');translation=np.array(ext.translation)
    raw=np.array(Image.open(CAP/'depth_raw_u16.png'))*r['depth_scale_m']
    aligned=np.array(Image.open(CAP/'depth_aligned_u16.png'))*r['depth_scale_m']
    rows=[]
    for v in range(0,raw.shape[0],7):
        for u in range(0,raw.shape[1],7):
            z=raw[v,u]
            if z<=0:continue
            p=np.array(rs.rs2_deproject_pixel_to_point(di,[u,v],z))
            sdk=np.array(rs.rs2_transform_point_to_point(ext,p.tolist()))
            numeric=rotation@p+translation
            pixel=np.array(rs.rs2_project_point_to_pixel(ci,sdk.tolist()))
            x,y=np.rint(pixel).astype(int)
            if not (2<=x<aligned.shape[1]-2 and 2<=y<aligned.shape[0]-2):continue
            patch=aligned[y-2:y+3,x-2:x+3];valid=patch[patch>0]
            wrong=rotation.T@p+translation
            wrong_pixel=rs.rs2_project_point_to_pixel(ci,wrong.tolist())
            rows.append(dict(u=u,v=v,x=x,y=y,transform_error=float(np.linalg.norm(sdk-numeric)),
                             min_depth_difference=float(np.min(abs(valid-z))) if valid.size else None,
                             wrong_rotation_pixel_error=float(np.linalg.norm(pixel-wrong_pixel))))
    errors=[x['min_depth_difference'] for x in rows if x['min_depth_difference'] is not None]
    times=r['frames_timing']
    delta=[abs(t['depth_ms']-t['color_ms']) for t in times]
    summary=dict(samples=len(rows),aligned_neighborhood_valid=len(errors),
        rotation_orthogonality_error=float(np.linalg.norm(rotation.T@rotation-np.eye(3))),
        rotation_determinant=float(np.linalg.det(rotation)),
        numpy_vs_sdk_transform_max_error_m=max(x['transform_error'] for x in rows),
        aligned_5x5_source_depth_difference_m_p50_p90_p99=np.percentile(errors,[50,90,99]).tolist(),
        aligned_samples_within_2mm_fraction=float(np.mean(np.array(errors)<=0.002)),
        transpose_rotation_mutant_error_px_p50_p90=np.percentile([x['wrong_rotation_pixel_error'] for x in rows],[50,90]).tolist(),
        timestamp_domain_match=all(t['depth_clock']==t['color_clock'] for t in times),
        rgb_depth_timestamp_separation_ms_p50_p95_max=np.percentile(delta,[50,95,100]).tolist(),
        scope='Cross-check recorded factory calibration and aligned-image reprojection, not independent physical calibration. 5x5 neighborhood accounts for SDK pixel splatting; compares original depth-camera Z values retained by alignment.',
        limitations=['No checkerboard or known-distance target measurement',
                     'RGB and depth are not simultaneous; moving scenes can be misregistered',
                     'Aligned depth stores source depth Z: deprojecting it as exact color-camera Z introduces geometric approximation',
                     'Transparent surfaces may give incorrect nonzero depth'])
    (OUT/'calibration_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    assert summary['numpy_vs_sdk_transform_max_error_m']<1e-5
    assert summary['rotation_orthogonality_error']<1e-5

if __name__=='__main__':main()
