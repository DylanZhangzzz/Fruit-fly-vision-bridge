"""Experimental RGB-D to right-eye L2 column drive; NOT a calibrated fly retina."""
import argparse
import csv
import gzip
import json
from pathlib import Path

import numpy as np
try:
    import pyrealsense2 as rs
except ImportError:
    rs = None  # Optional for pure projection tests; required by encode().
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def project_points(xyz, eye_x, fx, fy, cx, cy):
    """Virtual camera parallel to color camera, translated in metres along X."""
    z = xyz[:, 2]
    return np.column_stack((fx * (xyz[:, 0] - eye_x) / z + cx,
                            fy * xyz[:, 1] / z + cy))


def zbuffer(xyz, colors, eye_x, k):
    h, w = k['height'], k['width']
    xyz = np.asarray(xyz)
    colors = np.asarray(colors)
    usable = np.isfinite(xyz).all(axis=1) & (xyz[:, 2] > 0) & np.isfinite(colors).all(axis=1)
    xyz, colors = xyz[usable], colors[usable]
    uv = np.rint(project_points(xyz, eye_x, k['fx'], k['fy'], k['ppx'], k['ppy'])).astype(int)
    inside = (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    uv, points, colors = uv[inside], xyz[inside], colors[inside]
    # Nearer samples win when several measured points land on the same pixel.
    order = np.argsort(points[:, 2], kind='stable')
    flat = uv[order, 1] * w + uv[order, 0]
    _, first = np.unique(flat, return_index=True)
    chosen = order[first]
    image = np.full((h, w, 3), np.nan, dtype=np.float32)
    depth = np.full((h, w), np.nan, dtype=np.float32)
    image[uv[chosen, 1], uv[chosen, 0]] = colors[chosen]
    depth[uv[chosen, 1], uv[chosen, 0]] = points[chosen, 2]
    return image, depth


def column_mapping(k):
    """Identity-checked source columns; duplicate spatial positions are retained."""
    neurons = json.load(gzip.open(ROOT / 'fruit-fly-simulation/public/data/neurons.json.gz', 'rt'))
    ids = {str(r[0]): (i, r) for i, r in enumerate(neurons)}
    rows = list(csv.DictReader((ROOT/'camera_lab/data/ME_assigned_columns.csv').open()))
    rows = [r for r in rows if r['neuron_type'] == 'L2' and r['bodyId'] in ids
            and ids[r['bodyId']][1][1] == 'L2' and ids[r['bodyId']][1][3] == 'R']
    if not rows:
        raise ValueError('No verified right-eye L2 body IDs found')
    q = np.array([float(r['assigned_hex1']) for r in rows])
    r = np.array([float(r['assigned_hex2']) for r in rows])
    hx, hy = q - 0.5*r, np.sqrt(3)/2*r
    u = 12 + (hx-hx.min())/np.ptp(hx)*(k['width']-25)
    v = 12 + (hy-hy.min())/np.ptp(hy)*(k['height']-25)
    return [dict(bodyId=row['bodyId'], index=ids[row['bodyId']][0],
                 hex1=int(row['assigned_hex1']),hex2=int(row['assigned_hex2']),
                 u=float(px),v=float(py)) for row,px,py in zip(rows,u,v)]


def sample_channels(virtual, vz, mapping):
    """Shared production sampling for capture and controlled stimulus tests."""
    channels=[]
    for m in mapping:
        ix,iy=int(round(m['u'])),int(round(m['v']))
        patch=virtual[max(0,iy-6):iy+7,max(0,ix-6):ix+7]
        dep=vz[max(0,iy-6):iy+7,max(0,ix-6):ix+7]
        valid=np.isfinite(dep)&(dep>0)&np.isfinite(patch).all(axis=2)
        coverage=float(valid.mean()) if valid.size else 0.0
        if valid.sum()>=3:
            lum=float(np.mean(patch[valid] @ np.array([0.2126,0.7152,0.0722])))
            distance=float(np.median(dep[valid]))
            rate=float(120.0*(1-np.clip(lum,0,1)))
        else:
            lum,distance,rate=None,None,0.0
        channels.append(dict(m,luminance=lum,depth_m=distance,coverage=coverage,rate_hz=rate))
    return channels


def encode(capture, eye_x=0.03):
    capture = Path(capture)
    report = json.loads((capture / 'report.json').read_text())
    k = report['color_intrinsics']
    # Use original depth and actual extrinsics. SDK aligned depth retains depth-
    # sensor Z, so deprojecting it as color-camera Z is only an approximation.
    a = report['depth_intrinsics']
    intr = rs.intrinsics()
    for field in ['width', 'height', 'fx', 'fy', 'ppx', 'ppy']:
        setattr(intr, field, a[field])
    intr.coeffs = a['coeffs']
    intr.model = getattr(rs.distortion, a['model'].split('.')[-1])
    if k['model'] != 'distortion.none' and any(abs(c) > 1e-9 for c in k['coeffs']):
        raise ValueError('Virtual projection currently requires rectified color intrinsics')
    raw = np.asarray(Image.open(capture / 'depth_raw_u16.png'))
    rgb = np.asarray(Image.open(capture / 'rgb.png')).astype(np.float32) / 255
    z = raw * report['depth_scale_m']
    # Keep every native depth pixel; dropping 8/9 of samples caused avoidable
    # coverage loss after depth-to-color reprojection. Do not inpaint holes.
    y, x = np.mgrid[0:z.shape[0], 0:z.shape[1]]
    good = (z[y, x] >= 0.15) & (z[y, x] <= 5)
    x, y = x[good], y[good]
    depth_xyz = np.asarray([rs.rs2_deproject_pixel_to_point(intr, [float(u), float(v)], float(z[v,u]))
                      for u, v in zip(x, y)], dtype=np.float32)
    if len(depth_xyz) == 0:
        raise ValueError('No valid depth points in the selected range')
    ext=report['depth_to_color']
    rotation=np.asarray(ext['rotation']).reshape(3,3,order='F')
    xyz=depth_xyz @ rotation.T + np.asarray(ext['translation_m'])
    valid=np.isfinite(xyz).all(axis=1)&(xyz[:,2]>0)
    xyz=xyz[valid]
    color_uv=np.rint(project_points(xyz,0,k['fx'],k['fy'],k['ppx'],k['ppy'])).astype(int)
    inside=(color_uv[:,0]>=0)&(color_uv[:,0]<k['width'])&(color_uv[:,1]>=0)&(color_uv[:,1]<k['height'])
    xyz,color_uv=xyz[inside],color_uv[inside]
    # Keep visible points when several raw-depth samples project to one color pixel.
    order=np.argsort(xyz[:,2],kind='stable')
    _,first=np.unique(color_uv[order,1]*k['width']+color_uv[order,0],return_index=True)
    chosen=order[first];xyz,color_uv=xyz[chosen],color_uv[chosen]
    colors=rgb[color_uv[:,1],color_uv[:,0]]
    virtual, vz = zbuffer(xyz, colors, eye_x, k)
    channels = sample_channels(virtual, vz, column_mapping(k))
    result = dict(schema=2, capture=str(capture.resolve()), eye_x_m=eye_x,
                  mapping='Published right-eye L2 columns; camera-to-hex extent/orientation assumed',
                  encoding='Engineered dark drive 120*(1-luminance) Hz at L2; bypasses photoreceptors',
                  depth_role='Native-depth deprojection -> depth-to-color rigid transform -> color lookup -> virtual-view parallax/occlusion; no depth-to-rate gain',
                  limitations=['Not biological eye calibration','Not a validated L2 response model',
                               'Single eye, 3 cm virtual offset is a bench setting, not fly anatomy',
                               'Transparent/reflective surfaces may have wrong nonzero depth',
                               'Sparse sampling and disocclusion leave holes; insufficient samples give zero drive'],
                  measured_points=len(xyz), channels=channels)
    (capture/'neural_input.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    np.savez_compressed(capture/'spatial_encoding.npz', xyz_m=xyz, rgb=colors,
                        virtual_rgb=virtual, virtual_depth_m=vz)
    print(json.dumps({'channels':len(channels),'driven':sum(c['rate_hz']>0 for c in channels),
                      'measured_points':len(xyz),'output':str(capture/'neural_input.json')}))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    parser.add_argument('--eye-x',type=float,default=0.03)
    args=parser.parse_args()
    encode(args.capture,args.eye_x)
