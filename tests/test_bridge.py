import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from flyvisionbridge import Frame, map_frame, load_mapping
from flyvisionbridge.bridge import RESOLVED


def row(body,ray,status=RESOLVED):
    return dict(bodyId=str(body),reference_id='test-'+str(body),ray_head_xyz=ray,status=status)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.k=dict(width=8,height=6,fx=4.,fy=4.,ppx=3.,ppy=2.,coeffs=[0]*5)
        self.rgb=np.full((6,8,3),255,np.uint8)
        self.mapping=[row(1,[1,0,0]),row(2,[-1,0,0]),row(3,None,'MISSING_AUTHOR_BOUNDARY_COLUMN')]

    def frame(self,**kwargs):return Frame(self.rgb,self.k,1.,'TEST',**kwargs)

    def test_unknown_is_not_black(self):
        result=map_frame(self.frame(),self.mapping)['channels']
        self.assertAlmostEqual(result[0]['rgb_code_luminance'],1.)
        self.assertIsNone(result[1]['rgb_code_luminance'])
        self.assertIsNone(result[2]['rgb_code_luminance'])
        self.assertEqual(result[2]['rgb_status'],'MISSING_DIRECTION')

    def test_invalid_depth_does_not_hide_rgb(self):
        for value in [0.,-1.,np.nan,np.inf]:
            result=map_frame(self.frame(depth_color_z_m=np.full((6,8),value)),self.mapping)['channels'][0]
            self.assertIsNone(result['depth_color_z_m'])
            self.assertAlmostEqual(result['rgb_code_luminance'],1.)

    def test_color_z_units_and_gyro_sign(self):
        result=map_frame(self.frame(depth_color_z_m=np.full((6,8),2.),gyro_camera_rad_s=np.array([0,-1,0])),self.mapping)['channels'][0]
        self.assertEqual(result['depth_color_z_m'],2.)
        np.testing.assert_allclose(result['predicted_rotation_flow_head_per_s'],[0,-1,0])

    def test_rgb_order_and_position(self):
        self.rgb[2,3]=[255,0,0]
        result=map_frame(self.frame(),self.mapping)['channels'][0]
        self.assertAlmostEqual(result['rgb_code_luminance'],.2126)
        self.assertEqual(result['pixel_uv'],[3.,2.])

    def test_resolution_and_distortion_rejected(self):
        self.k['width']=9
        with self.assertRaises(ValueError):map_frame(self.frame(),self.mapping)
        self.k['width']=8;self.k['coeffs']=[.1,0,0,0,0]
        with self.assertRaises(ValueError):map_frame(self.frame(),self.mapping)

    def test_nonunit_rays_and_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):map_frame(self.frame(),[row(1,[2,0,0])])
        with self.assertRaises(ValueError):map_frame(self.frame(),[self.mapping[0]]*2)

    def test_reflection_rejected(self):
        with self.assertRaises(ValueError):map_frame(self.frame(),self.mapping,np.diag([-1,1,1]))

    def test_published_mapping_coverage(self):
        rows=load_mapping();self.assertEqual(len(rows),893)
        self.assertEqual(sum(r['status']==RESOLVED for r in rows),847)
        self.assertEqual(sum(r['ray_head_xyz'] is None for r in rows),46)

    def test_demo_is_portable_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'demo'
            command=[sys.executable,'-m','flyvisionbridge.cli','--demo','--output',str(output)]
            subprocess.run(command,check=True,capture_output=True)
            result=json.loads((output/'channels.json').read_text(encoding='utf8'))
            self.assertEqual(result['clock_domain'],'SYNTHETIC')
            self.assertEqual(len(result['channels']),893)
            self.assertTrue(any(c['rgb_status']=='OBSERVED' for c in result['channels']))
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
