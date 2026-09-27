import csv
import json
import unittest
from pathlib import Path
import numpy as np
from geometry import project_rays,sample_rgb,rotation_flow,ASSUMED_HEAD_FROM_CAMERA,require_resolved_crosswalk,rotation_checked

class BioMappingTests(unittest.TestCase):
    def setUp(self):self.k=dict(fx=100,fy=100,ppx=100,ppy=100,width=200,height=200)
    def test_directions_and_outside(self):
        rays=np.array([[1,0,0],[1,.1,0],[1,0,.1],[-1,0,0],[0,-1,0]])
        uv,valid=project_rays(rays,self.k)
        np.testing.assert_allclose(uv[:3],[[100,100],[90,100],[100,90]])
        self.assertEqual(valid.tolist(),[True,True,True,False,False])
    def test_reflection_rejected(self):
        with self.assertRaises(ValueError):rotation_checked(np.diag([-1,1,1]))
    def test_rotation_flow_sign(self):
        # Positive head yaw (toward left) makes static forward point flow right.
        f=rotation_flow([[1,0,0]],[0,-1,0])
        np.testing.assert_allclose(f,[[0,-1,0]])
    def test_rgb_not_gated_by_depth(self):
        uv,v=project_rays([[1,0,0],[-1,0,0]],self.k)
        values=sample_rgb(np.ones((200,200,3))*.4,uv,v)
        np.testing.assert_allclose(values[0],.4);self.assertTrue(np.isnan(values[1]).all())
    def test_source_unit_rays(self):
        with (Path(__file__).parent/'data/reference_rays.csv').open() as f:rows=list(csv.DictReader(f))
        rays=np.array([[float(r[k]) for k in ['ray_x_forward','ray_y_left','ray_z_up']] for r in rows])
        self.assertEqual(len(rows),778);np.testing.assert_allclose(np.linalg.norm(rays,axis=1),1,atol=1e-6)
    def test_no_false_malecns_injection(self):
        rows=json.loads((Path(__file__).parent/'data/malecns_crosswalk.json').read_text())
        self.assertEqual(len(rows),893)
        with self.assertRaisesRegex(ValueError,'unresolved'):require_resolved_crosswalk(rows)
    def test_depth_parallax_and_rotation_distinction(self):
        # Same ray under pure rotation is depth invariant; translation is not.
        ray=np.array([1.,-.2,.1]);R=ASSUMED_HEAD_FROM_CAMERA
        p=np.array([ray*.2,ray*2.]);c=p@R
        uv=np.c_[100*c[:,0]/c[:,2]+100,100*c[:,1]/c[:,2]+100]
        np.testing.assert_allclose(uv[0],uv[1])
        shifted=c-np.array([.03,0,0]);new=100*shifted[:,0]/shifted[:,2]+100
        self.assertGreater(abs(new[0]-uv[0,0]),abs(new[1]-uv[1,0]))
    def test_registration_and_no_extrapolation(self):
        from register_landmarks import fit_affine,interpolate_rays
        grid=np.array([[0,0],[1,0],[0,1],[1,1],[2,0],[2,1]],float)
        source=grid@np.array([[2.,.2],[.1,3.]])+[10,20]
        T=fit_affine(source,grid)
        np.testing.assert_allclose(np.c_[source,np.ones(6)]@T,grid,atol=1e-10)
        rays=np.c_[np.ones(6),grid];rays/=np.linalg.norm(rays,axis=1)[:,None]
        values=interpolate_rays([[0,0],[20,20]],grid,rays)
        np.testing.assert_allclose(values[0],rays[0]);self.assertIsNone(values[1])
    def test_degenerate_landmarks_rejected(self):
        from register_landmarks import fit_affine
        with self.assertRaises(ValueError):fit_affine([[0,0]]*6,[[0,0]]*6)

if __name__=='__main__':unittest.main()
