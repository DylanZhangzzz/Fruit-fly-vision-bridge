import unittest
import numpy as np
from encode_depth import project_points, zbuffer


class GeometryTests(unittest.TestCase):
    def test_same_ray_without_translation(self):
        p=np.array([[0.1,0,1],[0.2,0,2]])
        uv=project_points(p,0,100,100,50,50)
        np.testing.assert_allclose(uv,[[60,50],[60,50]])

    def test_nearer_point_has_more_parallax(self):
        p=np.array([[0,0,1],[0,0,2]])
        uv=project_points(p,0.1,100,100,50,50)
        np.testing.assert_allclose(uv[:,0],[40,45])

    def test_occlusion_and_missing_data(self):
        p=np.array([[0,0,2],[0,0,1]])
        colors=np.array([[1,0,0],[0,1,0]])
        k=dict(width=5,height=5,fx=1,fy=1,ppx=2,ppy=2)
        image,depth=zbuffer(p,colors,0,k)
        np.testing.assert_allclose(image[2,2],[0,1,0])
        self.assertEqual(depth[2,2],1)
        self.assertTrue(np.isnan(depth[0,0]))

    def test_invalid_points_cannot_occlude(self):
        p=np.array([[0,0,-1],[0,0,0],[np.nan,0,1],[0,0,1]])
        colors=np.array([[1,0,0],[1,0,0],[1,0,0],[0,1,0]])
        k=dict(width=5,height=5,fx=1,fy=1,ppx=2,ppy=2)
        image,depth=zbuffer(p,colors,0,k)
        np.testing.assert_allclose(image[2,2],[0,1,0])
        self.assertEqual(np.isfinite(depth).sum(),1)


if __name__=='__main__':
    unittest.main()
