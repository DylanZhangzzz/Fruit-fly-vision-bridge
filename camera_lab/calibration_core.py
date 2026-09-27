"""Candidate calibration solvers. Never overwrite production/device calibration."""
import cv2
import numpy as np

PATTERN=(8,6)  # internal corners; 9 by 7 printed squares

def object_points(square_m):
    if not 0.005 <= square_m <= 0.1:raise ValueError('Measured square must be 5..100 mm')
    a=np.zeros((48,3),np.float32)
    a[:,:2]=np.mgrid[:8,:6].T.reshape(-1,2)*square_m
    return a

def detect(rgb):
    grey=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    ok,c=cv2.findChessboardCornersSB(grey,PATTERN,flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        ok,c=cv2.findChessboardCorners(grey,PATTERN,flags=cv2.CALIB_CB_ADAPTIVE_THRESH|cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            c=cv2.cornerSubPix(grey,c.reshape(-1,1,2),(5,5),(-1,-1),
                              (cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_MAX_ITER,40,0.001))
    return c.astype(np.float32).reshape(-1,1,2) if ok else None

def solve_camera(corners,size,square_m):
    if len(corners)<15:raise ValueError('Need at least 15 distinct detected views')
    if any(np.asarray(c).shape!=(48,1,2) or not np.isfinite(c).all() for c in corners):
        raise ValueError('Invalid corner array')
    # Reject static captures / repeated images before the optimizer can overfit.
    unique=[]
    for c in corners:
        if all(np.sqrt(np.mean((c-u)**2))>5 for u in unique):unique.append(c)
    if len(unique)<15:raise ValueError('Need 15 distinct views; move/tilt the board')
    obj=object_points(square_m)
    train=[i for i in range(len(corners)) if i%5!=0]
    held=[i for i in range(len(corners)) if i%5==0]
    rms,K,d,rv,tv=cv2.calibrateCamera([obj]*len(train),[corners[i] for i in train],tuple(size),None,None)
    errors=[]; normals=[]
    for i,c in enumerate(corners):
        ok,r,t=cv2.solvePnP(obj,c,K,d)
        if not ok or t[2,0]<=0:raise ValueError('Invalid board pose')
        pred,_=cv2.projectPoints(obj,r,t,K,d)
        errors.append(float(np.sqrt(np.mean(np.sum((pred-c)**2,axis=2)))))
        normals.append(cv2.Rodrigues(r)[0][:,2])
    normals=np.array(normals); span=float(np.degrees(np.arccos(np.clip(normals@normals.T,-1,1))).max())
    points=np.concatenate(corners).reshape(-1,2)
    coverage=(np.ptp(points,axis=0)/np.array(size)).tolist()
    checks={'finite_parameters':bool(np.isfinite(K).all() and np.isfinite(d).all()),
            'reasonable_focal':bool(0.2*size[0]<K[0,0]<4*size[0] and 0.2*size[1]<K[1,1]<4*size[1]),
            'principal_point_in_image':bool(0<K[0,2]<size[0] and 0<K[1,2]<size[1]),
            'heldout_rms_under_1px':max(errors[i] for i in held)<1,
            'tilt_span_over_20deg':span>20,
            'coverage_over_half_image':min(coverage)>0.5}
    return dict(status='CANDIDATE_REQUIRES_PHYSICAL_REVIEW' if all(checks.values()) else 'REJECTED_QUALITY',
                camera_matrix=K.tolist(),distortion=d.ravel().tolist(),image_size=list(size),
                square_m=square_m,training_rms_px=float(rms),per_view_rms_px=errors,
                train_indices=train,heldout_indices=held,normal_span_deg=span,coverage_xy=coverage,
                checks=checks,holdout_note='Intrinsics fixed on held-out views; each view pose fitted to its own corners.',
                biological_eye_alignment='UNVERIFIED',applied=False)

POSES=('x+','x-','y+','y-','z+','z-')

def solve_imu(means,gyro_means,g=9.80665):
    if set(means)!=set(POSES):raise ValueError('All six labeled static poses required')
    raw=np.array([means[p] for p in POSES],float)
    if raw.shape!=(6,3) or not np.isfinite(raw).all():raise ValueError('Invalid IMU means')
    target=np.vstack([np.eye(3)[i//2]*(1 if i%2==0 else -1)*g for i in range(6)])
    cos=np.sum(raw*target,axis=1)/(np.linalg.norm(raw,axis=1)*g)
    if np.min(cos)<np.cos(np.deg2rad(8)):raise ValueError('Pose mislabeled or not aligned within 8 degrees')
    # Diagonal scale + bias only. Six hand-positioned poses cannot justify a full
    # unconstrained alignment matrix with apparent zero residual.
    bias=np.array([(raw[2*i,i]+raw[2*i+1,i])/2 for i in range(3)])
    scale=np.array([2*g/(raw[2*i,i]-raw[2*i+1,i]) for i in range(3)])
    if np.any((scale<0.8)|(scale>1.2)):raise ValueError('Implausible scale: inspect fixture/labels')
    corrected=(raw-bias)*scale
    residual=np.linalg.norm(corrected-target,axis=1)
    return dict(status='CANDIDATE_NEEDS_INDEPENDENT_POSES',accel_bias_m_s2=bias.tolist(),
                accel_diagonal_scale=scale.tolist(),gyro_bias_rad_s=np.mean(gyro_means,axis=0).tolist(),
                gravity_reference_m_s2=g,per_pose_vector_residual_m_s2=residual.tolist(),
                formula='corrected_specific_force = (sdk_accel - bias) * scale',
                scope='Correction on SDK output, not raw chip data. No gyro scale, cross-axis or time/extrinsic calibration.',
                absolute_yaw='UNOBSERVABLE',applied=False)
