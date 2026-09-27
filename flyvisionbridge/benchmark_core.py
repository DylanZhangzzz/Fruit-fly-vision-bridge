"""Deterministic stimuli, causal L2 dynamics and explicit spatial support.

Only NumPy is needed for stimuli and L2. Spatial interpolation additionally
uses SciPy. This module does not import external models or open hardware.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .bridge import load_mapping, RESOLVED
from camera_lab.biomapping.geometry import ASSUMED_HEAD_FROM_CAMERA, project_rays

PROTOCOL = Path(__file__).with_name('benchmark_protocol.json')


def protocol():
    return json.loads(PROTOCOL.read_text(encoding='utf8'))


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def synthetic_intrinsics(p):
    w, h = p['synthetic_width'], p['synthetic_height']
    f = w / (2*np.tan(np.deg2rad(p['synthetic_horizontal_fov_degrees']/2)))
    return dict(width=w, height=h, fx=f, fy=f, ppx=(w-1)/2,
                ppy=(h-1)/2, coeffs=[0.]*5, source='SYNTHETIC_ASSUMED_PINHOLE')


def stimulus(name, p=None):
    p = protocol() if p is None else p
    if name not in p['cases']:
        raise ValueError(f'Unknown stimulus {name}')
    dt = p['frame_dt_s']
    times = np.arange(round(p['duration_s']/dt))*dt
    h, w = p['synthetic_height'], p['synthetic_width']
    yy, xx = np.mgrid[:h, :w]
    gray = np.full((len(times), h, w), p['background_code'], np.uint8)
    for i, t in enumerate(times):
        elapsed = t-p['onset_s']
        active = p['onset_s']-1e-9 <= t < p['offset_s']-1e-9
        if name.startswith('flash'):
            duration = .2 if '200ms' in name else .02
            if -1e-9 <= elapsed < duration-1e-9:
                gray[i] = p['dark_code'] if 'dark' in name else p['light_code']
        elif active and name.startswith('grating'):
            direction = 1 if name.endswith('right') else -1
            wave = np.sin(2*np.pi*(xx-direction*p['motion_pixels_per_second']*elapsed)/p['stripe_period_pixels'])
            gray[i] = np.rint(p['background_code']+96*wave).astype(np.uint8)
        elif active and name.startswith('edge'):
            axis = xx if name.endswith(('left','right')) else yy
            size = w if name.endswith(('left','right')) else h
            frac = elapsed/(p['offset_s']-p['onset_s'])
            increasing = name.endswith(('right','down'))
            boundary = size*(frac if increasing else 1-frac)
            dark = axis < boundary if increasing else axis > boundary
            gray[i] = np.where(dark, p['dark_code'], p['light_code'])
        elif active and name in ('loom','recede'):
            frac = elapsed/(p['offset_s']-p['onset_s'])
            if name == 'recede': frac = 1-frac
            radius = 10+150*frac
            dark = (xx-(w-1)/2)**2+(yy-(h-1)/2)**2 < radius**2
            gray[i][dark] = p['dark_code']
    return times, np.repeat(gray[..., None], 3, axis=-1)


def bilinear_movie(gray, uv):
    """Sample T,H,W floating arrays; absent positions stay NaN."""
    gray, uv = np.asarray(gray), np.asarray(uv, float)
    h, w = gray.shape[1:]
    good = np.isfinite(uv).all(axis=1) & (uv[:,0]>=0) & (uv[:,0]<w-1) & (uv[:,1]>=0) & (uv[:,1]<h-1)
    out = np.full((len(gray), len(uv)), np.nan)
    x,y = uv[good].T; ix,iy = x.astype(int),y.astype(int); dx,dy = x-ix,y-iy
    out[:,good] = (gray[:,iy,ix]*(1-dx)*(1-dy)+gray[:,iy,ix+1]*dx*(1-dy)+
                  gray[:,iy+1,ix]*(1-dx)*dy+gray[:,iy+1,ix+1]*dx*dy)
    return out


def sample_columns(rgb, intrinsics, mapping=None, head_from_camera=ASSUMED_HEAD_FROM_CAMERA):
    """All published IDs kept, including unknown directions and off-camera rays."""
    from .bridge import Frame
    Frame(rgb[0], intrinsics, 0., 'REPLAY').validate()
    rows = load_mapping() if mapping is None else mapping
    if len({r['bodyId'] for r in rows})!=len(rows):raise ValueError('Duplicate body IDs')
    uv = np.full((len(rows),2), np.nan)
    ids = [i for i,r in enumerate(rows) if r['status']==RESOLVED]
    if ids:
        rays=np.asarray([rows[i]['ray_head_xyz'] for i in ids],float)
        if not np.isfinite(rays).all() or not np.allclose(np.linalg.norm(rays,axis=1),1):
            raise ValueError('Published rays must be finite unit vectors')
        projected, visible = project_rays(rays, intrinsics, head_from_camera)
        uv[np.asarray(ids)[visible]] = projected[visible]
    gray = np.asarray(rgb, float) @ np.array([.2126,.7152,.0722]) / 255
    samples = bilinear_movie(gray, uv)
    return rows, uv, samples


def l2_response(samples, dt, parameters=None):
    """Fixed-parameter RK4 integration of the author's two-state equation family.

    Missing timepoints permanently invalidate that channel's state for this
    sequence: no silent reset, imputation or recovery across an unknown history.
    Samples are held over [t,t+dt); output is at the right edge.
    """
    p = protocol()['l2'] if parameters is None else parameters
    a = np.asarray(samples, float)
    if a.ndim != 2 or not np.isfinite(dt) or dt<=0:
        raise ValueError('Expected time x channels and a positive finite dt')
    if np.any((a[np.isfinite(a)]<0) | (a[np.isfinite(a)]>1)):
        raise ValueError('Expected camera-code samples in [0,1]')
    v,y = np.zeros(a.shape[1]),np.zeros(a.shape[1])
    out = np.full_like(a,np.nan)
    alive = np.ones(a.shape[1],bool)
    n = int(np.ceil(dt/p['integration_max_step_s'])); step=dt/n
    def rhs(v,y,d):
        return ((-v-p['feedback_w']*y-d)/p['tv_s'],
                (-y+v*np.where(v>0,1-p['asymmetry_g'],p['asymmetry_g']))/p['ty_s'])
    for i,s in enumerate(a):
        alive &= np.isfinite(s)
        contrast = np.where(alive,(s-128/255)/(128/255),0)
        d = contrast*np.where(contrast>0,p['light_drive'],p['dark_drive'])
        for _ in range(n):
            k1,l1=rhs(v,y,d);k2,l2=rhs(v+step*k1/2,y+step*l1/2,d)
            k3,l3=rhs(v+step*k2/2,y+step*l2/2,d);k4,l4=rhs(v+step*k3,y+step*l3,d)
            v+=step*(k1+2*k2+2*k3+k4)/6; y+=step*(l1+2*l2+2*l3+l4)/6
        out[i,alive]=v[alive]
    return out


def interpolation_map(source_uv, target_uv):
    """Barycentric IMAGE-space readout. No extrapolation or cell-ID assertion."""
    from scipy.spatial import Delaunay
    source_uv,target_uv = np.asarray(source_uv,float),np.asarray(target_uv,float)
    triangulation = Delaunay(source_uv)
    vertices = np.full((len(target_uv),3),-1,int)
    weights = np.full((len(target_uv),3),np.nan)
    finite=np.isfinite(target_uv).all(axis=1)
    ids=np.flatnonzero(finite)
    simplex=triangulation.find_simplex(target_uv[finite])
    ids,simplex=ids[simplex>=0],simplex[simplex>=0]
    transform=triangulation.transform[simplex]
    b=np.einsum('ijk,ik->ij',transform[:,:2],target_uv[ids]-transform[:,2])
    weights[ids]=np.c_[b,1-b.sum(axis=1)]
    vertices[ids]=triangulation.simplices[simplex]
    return vertices,weights


def interpolate_responses(responses, vertices, weights):
    out=np.full((len(responses),len(vertices)),np.nan)
    good=(vertices>=0).all(axis=1)&np.isfinite(weights).all(axis=1)
    out[:,good]=np.einsum('tij,ij->ti',responses[:,vertices[good]],weights[good])
    return out
