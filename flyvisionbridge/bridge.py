"""Camera-independent frame contract and unknown-preserving ray sampling."""
from dataclasses import dataclass
import json
from pathlib import Path
import numpy as np
from camera_lab.biomapping.geometry import (
    ASSUMED_HEAD_FROM_CAMERA, project_rays, sample_rgb, rotation_flow, rotation_checked,
)

MAPPING = Path(__file__).resolve().parents[1] / "camera_lab/biomapping/data/malecns_author_crosswalk.json"
RESOLVED = "AUTHOR_PUBLISHED_COLUMN_CORRESPONDENCE"


@dataclass
class Frame:
    """Rectified RGB uint8; optional depth is color-camera Z in metres.

    gyro_camera_rad_s is an already time-associated, color-camera-frame angular
    velocity. Supplying it does not establish accurate synchronization or bias
    calibration. No depth or IMU is inferred for an RGB-only camera.
    """
    rgb: np.ndarray
    intrinsics: dict
    timestamp_s: float
    clock_domain: str
    depth_color_z_m: np.ndarray | None = None
    gyro_camera_rad_s: np.ndarray | None = None

    def validate(self):
        a = np.asarray(self.rgb)
        if a.ndim != 3 or a.shape[2] != 3 or a.dtype != np.uint8:
            raise ValueError("RGB must be H x W x 3 uint8 in RGB order.")
        k = self.intrinsics
        if (k['height'], k['width']) != a.shape[:2]:
            raise ValueError("Intrinsics resolution does not match RGB.")
        if not np.isfinite([k[x] for x in ['fx', 'fy', 'ppx', 'ppy']]).all() or min(k['fx'], k['fy']) <= 0:
            raise ValueError("Intrinsics must be finite with positive focal lengths.")
        if any(k.get('coeffs', [])):
            raise ValueError("Rectify the RGB image and update intrinsics before mapping.")
        if not np.isfinite(self.timestamp_s) or not self.clock_domain:
            raise ValueError("A finite timestamp and explicit clock domain are required.")
        if self.depth_color_z_m is not None and np.shape(self.depth_color_z_m) != a.shape[:2]:
            raise ValueError("Depth must be registered color-camera Z with the RGB shape.")
        if self.gyro_camera_rad_s is not None:
            g = np.asarray(self.gyro_camera_rad_s)
            if g.shape != (3,) or not np.isfinite(g).all():
                raise ValueError("Gyro must have three finite values in rad/s.")


def load_mapping(path=MAPPING):
    return json.loads(Path(path).read_text(encoding='utf8'))


def load_eye_mapping(eyes='both'):
    """Explicit eye selection; legacy load_mapping/map_frame defaults remain right-only."""
    if eyes not in ['left','right','both']:raise ValueError('eyes must be left, right or both')
    rows=[]
    if eyes in ['left','both']:
        rows+=load_mapping(MAPPING.with_name('malecns_left_crosswalk.json'))
    if eyes in ['right','both']:
        rows+=[dict(r,eye='R') for r in load_mapping()]
    if any(r.get('eye') not in ['L','R'] for r in rows):raise ValueError('Missing eye identity')
    if len({r['bodyId'] for r in rows})!=len(rows):raise ValueError('Duplicate binocular body ID')
    return rows


def map_frame(frame, mapping=None, head_from_camera=ASSUMED_HEAD_FROM_CAMERA):
    frame.validate()
    rotation_checked(head_from_camera)
    rows = load_mapping() if mapping is None else mapping
    if len({r['bodyId'] for r in rows}) != len(rows):
        raise ValueError("Duplicate body IDs in mapping.")
    resolved = [r for r in rows if r['status'] == RESOLVED]
    rays = np.asarray([r['ray_head_xyz'] for r in resolved], float).reshape(-1, 3)
    if not np.isfinite(rays).all() or not np.allclose(np.linalg.norm(rays, axis=1), 1, atol=1e-6):
        raise ValueError("Published rays must be finite unit vectors.")
    uv, visible = project_rays(rays, frame.intrinsics, head_from_camera)
    colors = sample_rgb(frame.rgb.astype(float)/255, uv, visible)
    flows = rotation_flow(rays, frame.gyro_camera_rad_s, head_from_camera) if frame.gyro_camera_rad_s is not None else None
    by_id = {}
    for i, row in enumerate(resolved):
        depth = None
        if visible[i] and frame.depth_color_z_m is not None:
            x, y = np.rint(uv[i]).astype(int)
            value = float(frame.depth_color_z_m[y, x])
            if np.isfinite(value) and value > 0:
                depth = value
        by_id[row['bodyId']] = dict(
            bodyId=row['bodyId'], eye=row.get('eye','R'), reference_id=row['reference_id'],
            mapping_status=row['status'], rgb_status='OBSERVED' if visible[i] else 'OUTSIDE_CAMERA_FOV',
            pixel_uv=uv[i].tolist() if visible[i] else None,
            rgb_code_luminance=float(colors[i] @ [.2126, .7152, .0722]) if visible[i] else None,
            depth_color_z_m=depth,
            predicted_rotation_flow_head_per_s=flows[i].tolist() if flows is not None else None,
        )
    channels = [by_id.get(r['bodyId'], dict(bodyId=r['bodyId'], eye=r.get('eye','R'), reference_id=None,
        mapping_status=r['status'], rgb_status='MISSING_DIRECTION', pixel_uv=None,
        rgb_code_luminance=None, depth_color_z_m=None, predicted_rotation_flow_head_per_s=None)) for r in rows]
    return dict(timestamp_s=frame.timestamp_s, clock_domain=frame.clock_domain,
        head_from_camera=np.asarray(head_from_camera).tolist(),
        mounting='Explicit transform; default is an assumed bench orientation, not biological calibration',
        observable='Weighted camera RGB code, not linear radiance, membrane voltage or firing rate',
        imu_status='SUPPLIED_CAMERA_FRAME_UNVERIFIED_TIMING' if flows is not None else 'UNAVAILABLE',
        depth_status='SUPPLIED_REGISTERED_Z_UNVERIFIED_GEOMETRY' if frame.depth_color_z_m is not None else 'UNAVAILABLE',
        channels=channels)
