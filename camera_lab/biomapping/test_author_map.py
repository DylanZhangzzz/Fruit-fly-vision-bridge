"""Independent joins, schema guards and per-direction stimulus tests."""
import json
import unittest
import numpy as np
import pandas as pd
from import_author_map import BASE, XLSX, join_columns, STATUS
from geometry import project_rays, ASSUMED_HEAD_FROM_CAMERA

class AuthorMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table=pd.read_excel(XLSX)
        cls.targets=json.loads((BASE/'data/malecns_crosswalk.json').read_text())
        cls.rows=join_columns(cls.targets,cls.table)

    def test_join_independent_of_row_order(self):
        other=join_columns(list(reversed(self.targets)),self.table.sample(frac=1,random_state=4))
        self.assertEqual({r['bodyId']:r for r in self.rows},{r['bodyId']:r for r in other})

    def test_coverage_no_extrapolation(self):
        self.assertEqual(sum(r['status']==STATUS for r in self.rows),847)
        missing=[r for r in self.rows if r['status']!=STATUS]
        self.assertEqual(len(missing),46)
        self.assertTrue(all(r['ray_head_xyz'] is None for r in missing))

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):join_columns(self.targets,pd.concat([self.table,self.table.iloc[:1]]))

    def test_axis_and_column_corruption_detected(self):
        for key in ['hex1','y','theta']:
            bad=self.table.copy();bad.loc[0,key]+=1
            with self.assertRaises(ValueError):join_columns(self.targets,bad)

    def test_csv_independent_export(self):
        csv=pd.read_csv(BASE/'source/eyemap_archive/docs/data/eyemap_mcns_f20240701/right.csv')
        np.testing.assert_allclose(csv[['x','y','z']],self.table[['x','y','z']],atol=5.1e-7)
        self.assertEqual(list(zip(csv.hex1,csv.hex2)),list(zip(self.table.hex1,self.table.hex2)))

    def test_every_column_spherical_point_stimulus(self):
        # A narrow angular spot at each author's ray must peak at that column.
        # This checks encoder addressing, NOT independent biological accuracy.
        v=self.table[['x','y','z']].to_numpy()
        similarity=v@v.T
        np.testing.assert_array_equal(similarity.argmax(axis=1),np.arange(len(v)))
        off=similarity.copy();np.fill_diagonal(off,-1)
        self.assertGreater(float(np.degrees(np.arccos(np.clip(off.max(),-1,1)))),0.1)

    def test_shared_column_is_preserved(self):
        pair=[r for r in self.rows if r['bodyId'] in ['43130','56150']]
        self.assertEqual(len(pair),2)
        self.assertEqual(pair[0]['ray_head_xyz'],pair[1]['ray_head_xyz'])

    def test_camera_projection_roundtrip(self):
        v=self.table[['x','y','z']].to_numpy()
        k=dict(fx=616.,fy=615.,ppx=327.,ppy=241.,width=640,height=480)
        uv,valid=project_rays(v,k)
        c=np.c_[(uv[valid,0]-k['ppx'])/k['fx'],(uv[valid,1]-k['ppy'])/k['fy'],np.ones(valid.sum())]
        head=c@ASSUMED_HEAD_FROM_CAMERA.T
        head/=np.linalg.norm(head,axis=1)[:,None]
        np.testing.assert_allclose(head,v[valid],atol=1e-12)

if __name__=='__main__':unittest.main()
