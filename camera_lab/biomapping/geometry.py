"""Explicit coordinate operations for a reference-eye prototype, not L2 biology."""
import numpy as np

# Color camera: right, down, forward -> eye frame: forward, left, up.
ASSUMED_HEAD_FROM_CAMERA=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])

def rotation_checked(R):
    R=np.asarray(R,float)
    if R.shape!=(3,3) or not np.isfinite(R).all() or not np.allclose(R@R.T,np.eye(3),atol=1e-6) or not np.isclose(np.linalg.det(R),1):
        raise ValueError('Need a proper rotation, not a reflection or scaling')
    return R

def project_rays(rays_head,k,R_head_camera=ASSUMED_HEAD_FROM_CAMERA):
    R=rotation_checked(R_head_camera); rays=np.asarray(rays_head,float)
    camera=rays@R
    z=camera[:,2];uv=np.full((len(camera),2),np.nan)
    front=np.isfinite(camera).all(axis=1)&(z>1e-8)
    uv[front]=np.c_[k['fx']*camera[front,0]/z[front]+k['ppx'],k['fy']*camera[front,1]/z[front]+k['ppy']]
    visible=front&(uv[:,0]>=0)&(uv[:,0]<k['width']-1)&(uv[:,1]>=0)&(uv[:,1]<k['height']-1)
    return uv,visible

def rotation_flow(rays_head,omega_camera,R_head_camera=ASSUMED_HEAD_FROM_CAMERA):
    omega=rotation_checked(R_head_camera)@np.asarray(omega_camera)
    return -np.cross(omega,np.asarray(rays_head))

def sample_rgb(rgb,uv,visible):
    values=np.full((len(uv),3),np.nan)
    for i in np.flatnonzero(visible):
        x,y=uv[i];ix,iy=int(x),int(y); dx,dy=x-ix,y-iy
        values[i]=(rgb[iy,ix]*(1-dx)*(1-dy)+rgb[iy,ix+1]*dx*(1-dy)+
                   rgb[iy+1,ix]*(1-dx)*dy+rgb[iy+1,ix+1]*dx*dy)
    return values

def require_resolved_crosswalk(rows):
    if not rows or any(r.get('status')!='VERIFIED_CORRESPONDENCE' or not r.get('reference_id') or
                       not r.get('evidence') or r.get('ray_head_xyz') is None for r in rows):
        raise ValueError('MaleCNS angular correspondence unresolved; brain injection disabled')
    if len({r['bodyId'] for r in rows})!=len(rows):raise ValueError('Duplicate body IDs')
    rays=np.asarray([r['ray_head_xyz'] for r in rows],float)
    if rays.shape!=(len(rows),3) or not np.isfinite(rays).all() or not np.allclose(np.linalg.norm(rays,axis=1),1,atol=1e-6):
        raise ValueError('Invalid unit directions')
    return rays
