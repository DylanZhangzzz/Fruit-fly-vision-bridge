"""Synthetic known-ground-truth checks, explicitly not real-device calibration."""
import json
import unittest
from pathlib import Path
import cv2
import numpy as np
from calibration_core import object_points,solve_camera,solve_imu,POSES,detect

class CalibrationTests(unittest.TestCase):
    def test_known_camera_and_heldout(self):
        rng=np.random.default_rng(13)
        K=np.array([[610.,0,320],[0,615,240],[0,0,1]])
        obj=object_points(.02); corners=[]
        for i in range(25):
            r=np.array([rng.uniform(-.6,.6),rng.uniform(-.6,.6),rng.uniform(-.2,.2)])
            t=np.array([rng.uniform(-.12,-.02),rng.uniform(-.09,0),rng.uniform(.32,.55)])
            c,_=cv2.projectPoints(obj,r,t,K,np.zeros(5))
            c+=rng.normal(0,.03,c.shape); corners.append(c.astype(np.float32))
        result=solve_camera(corners,(640,480),.02)
        self.assertLess(abs(result['camera_matrix'][0][0]-610),5)
        self.assertLess(abs(result['camera_matrix'][1][1]-615),5)
        self.assertEqual(len(result['heldout_indices']),5)
        self.assertTrue(result['checks']['heldout_rms_under_1px'])
        self.assertTrue(result['checks']['tilt_span_over_20deg'])
        out=Path(__file__).parent/'calibration';out.mkdir(exist_ok=True)
        result['data_origin']='SYNTHETIC_NOT_CAMERA'; (out/'synthetic_camera_test.json').write_text(json.dumps(result,indent=2))

    def test_repeated_views_rejected(self):
        c=np.zeros((48,1,2),np.float32)
        with self.assertRaisesRegex(ValueError,'distinct'):solve_camera([c]*20,(640,480),.02)

    def test_imu_known_bias_and_scale(self):
        bias=np.array([.12,-.2,.08]); scale=np.array([1.02,.98,1.03]); g=9.80665
        means={p:(np.eye(3)[i//2]*(1 if i%2==0 else -1)*g/scale+bias).tolist() for i,p in enumerate(POSES)}
        result=solve_imu(means,[[.001,.002,-.003]]*6)
        np.testing.assert_allclose(result['accel_bias_m_s2'],bias,atol=1e-10)
        np.testing.assert_allclose(result['accel_diagonal_scale'],scale,atol=1e-10)
        means['x+'],means['x-']=means['x-'],means['x+']
        with self.assertRaisesRegex(ValueError,'mislabeled'):solve_imu(means,[[0,0,0]]*6)

    def test_missing_poses_rejected(self):
        with self.assertRaisesRegex(ValueError,'six'):solve_imu({'x+':[9.8,0,0]},[[0,0,0]])

    def test_exported_board_detectable(self):
        from PIL import Image
        image=np.array(Image.open(Path(__file__).parent/'calibration/target/checkerboard_preview.png'))
        self.assertEqual(detect(image).shape,(48,1,2))

    def test_depth_plane_known_offset(self):
        import tempfile
        from PIL import Image
        from calibrate import depth_check
        K=np.array([[600.,0,320],[0,600,240],[0,0,1]])
        c,_=cv2.projectPoints(object_points(.02),np.zeros(3),np.array([-.07,-.05,1.]),K,np.zeros(5))
        meta=dict(square_mm=20,depth_scale_m=.001,
            depth_intrinsics=dict(width=640,height=480,fx=600,fy=600,ppx=320,ppy=240,model='distortion.none',coeffs=[0]*5),
            depth_to_color=dict(rotation=np.eye(3).ravel().tolist(),translation_m=[0,0,0]),
            views=[dict(depth='depth.png',corners=c.tolist())])
        result=dict(camera_matrix=K.tolist(),distortion=[0]*5,heldout_indices=[0])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            Image.fromarray(np.full((480,640),1020,np.uint16)).save(path/'depth.png')
            report=depth_check(path,meta,result)
            self.assertAlmostEqual(report['views'][0]['signed_median_m'],.02,places=5)
            Image.fromarray(np.zeros((480,640),np.uint16)).save(path/'depth.png')
            self.assertEqual(depth_check(path,meta,result)['views'][0]['status'],'NO_VALID_DEPTH')

if __name__=='__main__':unittest.main()
