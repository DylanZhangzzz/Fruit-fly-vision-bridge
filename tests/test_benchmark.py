"""Independent checks for support, causality, numerical accuracy and stimuli."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from flyvisionbridge.benchmark_core import (protocol,stimulus,l2_response,sample_columns,
    interpolation_map,interpolate_responses)
from flyvisionbridge.bridge import RESOLVED


class BenchmarkTests(unittest.TestCase):
    def test_binocular_live_default_does_not_expand_frozen_benchmark(self):
        from flyvisionbridge.benchmark_core import synthetic_intrinsics
        from flyvisionbridge.bridge import load_eye_mapping
        p=protocol()
        rgb=np.full((1,p['synthetic_height'],p['synthetic_width'],3),p['background_code'],np.uint8)
        rows,uv,samples=sample_columns(rgb,synthetic_intrinsics(p))
        self.assertEqual(len(rows),893)
        self.assertEqual(samples.shape,(1,893))
        self.assertEqual(int(np.isfinite(uv).all(axis=1).sum()),252)
        left_ids={r['bodyId'] for r in load_eye_mapping('left')}
        self.assertTrue(left_ids.isdisjoint(r['bodyId'] for r in rows))

    def test_nominal_flash_duration_and_determinism(self):
        for name,count in [('flash_dark_20ms',1),('flash_light_200ms',10)]:
            t,rgb=stimulus(name)
            self.assertEqual(int(np.any(rgb!=128,axis=(1,2,3)).sum()),count)
            np.testing.assert_array_equal(rgb,stimulus(name)[1])

    def test_motion_direction_is_known_from_rendering(self):
        for name,axis,sign in [('edge_right',1,1),('edge_left',1,-1),('edge_down',0,1),('edge_up',0,-1)]:
            _,rgb=stimulus(name)
            boundaries=[]
            for i in [25,35,45]:
                line=rgb[i,200,:,0] if axis==1 else rgb[i,:,200,0]
                boundaries.append(np.flatnonzero(np.diff(line.astype(float)))[0])
            self.assertTrue(np.all(sign*np.diff(boundaries)>0))

    def test_no_feedback_matches_closed_form(self):
        p=copy.deepcopy(protocol()['l2']);p['feedback_w']=0
        samples=np.full((30,1),.25);dt=.02
        result=l2_response(samples,dt,p)[:,0]
        drive=(.25-128/255)/(128/255)*p['dark_drive']
        expected=-drive*(1-np.exp(-np.arange(1,31)*dt/p['tv_s']))
        np.testing.assert_allclose(result,expected,rtol=1e-6,atol=2e-7)

    def test_no_future_input_or_unknown_history_leak(self):
        a=np.full((30,2),128/255);b=a.copy();b[20:]=0
        np.testing.assert_array_equal(l2_response(a,.02)[:20],l2_response(b,.02)[:20])
        a[10,0]=np.nan;result=l2_response(a,.02)
        self.assertTrue(np.isnan(result[10:,0]).all())
        self.assertTrue(np.isfinite(result[:,1]).all())

    def test_unit_and_shape_errors(self):
        for a,dt in [(np.zeros(3),.02),(np.ones((3,1))*255,.02),(np.zeros((3,1)),0)]:
            with self.assertRaises(ValueError):l2_response(a,dt)

    def test_spatial_unknowns_and_rgb_order(self):
        rgb=np.zeros((2,8,8,3),np.uint8);rgb[:,:,:,0]=255
        rows=[dict(bodyId=1,status=RESOLVED,ray_head_xyz=[1,0,0]),
              dict(bodyId=2,status=RESOLVED,ray_head_xyz=[-1,0,0]),
              dict(bodyId=3,status='MISSING',ray_head_xyz=None)]
        k=dict(width=8,height=8,fx=4.,fy=4.,ppx=3.5,ppy=3.5,coeffs=[0]*5)
        _,uv,samples=sample_columns(rgb,k,rows)
        np.testing.assert_allclose(samples[:,0],.2126)
        self.assertTrue(np.isnan(samples[:,1:]).all())

    @unittest.skipUnless(importlib.util.find_spec('scipy'),'SciPy optional')
    def test_image_interpolation_preserves_affine_field_and_unknown(self):
        src=np.array([[0,0],[1,0],[0,1],[1,1]],float)
        dst=np.array([[.2,.7],[2,2],[np.nan,0]])
        vertices,weights=interpolation_map(src,dst)
        out=interpolate_responses((2*src[:,0]-3*src[:,1]+7)[None],vertices,weights)
        self.assertAlmostEqual(out[0,0],5.3)
        self.assertTrue(np.isnan(out[0,1:]).all())

    def test_archive_traversal_rejected(self):
        from scripts.fetch_benchmark_models import safe_extract
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('../outside.txt','x')
            with self.assertRaises(ValueError):safe_extract(path,Path(folder)/'data')

    def test_feedback_numerical_convergence(self):
        samples=np.full((60,2),128/255);samples[10:20]=[32/255,224/255]
        p=copy.deepcopy(protocol()['l2'])
        reference=l2_response(samples,.02,p)
        p['integration_max_step_s']/=2
        np.testing.assert_allclose(reference,l2_response(samples,.02,p),rtol=2e-5,atol=2e-6)

    def test_invalid_spatial_identity_rejected(self):
        rgb=np.zeros((2,8,8,3),np.uint8)
        k=dict(width=8,height=8,fx=4.,fy=4.,ppx=3.,ppy=3.,coeffs=[0]*5)
        row=dict(bodyId=1,status=RESOLVED,ray_head_xyz=[2,0,0])
        with self.assertRaises(ValueError):sample_columns(rgb,k,[row])
        row['ray_head_xyz']=[1,0,0]
        with self.assertRaises(ValueError):sample_columns(rgb,k,[row,row])


if __name__=='__main__':unittest.main()
