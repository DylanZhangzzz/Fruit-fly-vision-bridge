import importlib.util
import json
import unittest
import numpy as np
from flyvisionbridge import Frame,map_frame,load_eye_mapping
from flyvisionbridge.bridge import RESOLVED
from flyvisionbridge.live_core import approximate_intrinsics,engineer_rates


class BinocularBridgeTests(unittest.TestCase):
    def test_inventory_coverage_and_unknowns(self):
        rows=load_eye_mapping();self.assertEqual(len(rows),1779)
        self.assertEqual(len({r['bodyId'] for r in rows}),1779)
        for eye,total,missing in [('left',886,39),('right',893,46)]:
            subset=load_eye_mapping(eye);self.assertEqual(len(subset),total)
            self.assertEqual(sum(r['status']==RESOLVED for r in subset),847)
            self.assertEqual(sum(r['ray_head_xyz'] is None for r in subset),missing)
        with self.assertRaises(ValueError):load_eye_mapping('mirrored')

    def test_single_image_samples_each_eye_at_its_own_position(self):
        k=approximate_intrinsics(640,480,90)
        rgb=np.full((480,640,3),255,np.uint8);rgb[:,:320]=0
        result=map_frame(Frame(rgb,k,0,'SYNTHETIC'),load_eye_mapping())
        channels=result['channels'];rates=engineer_rates(result)
        left=[c for c in rates if c['eye']=='L'];right=[c for c in rates if c['eye']=='R']
        self.assertGreater(len(left),0);self.assertGreater(len(right),0)
        self.assertFalse({c['bodyId'] for c in left}&{c['bodyId'] for c in right})
        self.assertGreater(np.mean([c['rate_hz'] for c in left]),np.mean([c['rate_hz'] for c in right])+30)
        # Deliberately flip the image: the side contrast must reverse.
        flipped=engineer_rates(map_frame(Frame(rgb[:,::-1].copy(),k,0,'SYNTHETIC'),load_eye_mapping()))
        means={e:np.mean([c['rate_hz'] for c in flipped if c['eye']==e]) for e in ['L','R']}
        self.assertGreater(means['R'],means['L']+30)
        unknown={c['bodyId'] for c in channels if c['rgb_status']!='OBSERVED'}
        self.assertFalse(unknown&{c['bodyId'] for c in rates})

    def test_missing_and_outside_both_eyes_remain_unknown(self):
        k=approximate_intrinsics(20,20,10)
        mapped=map_frame(Frame(np.zeros((20,20,3),np.uint8),k,0,'SYNTHETIC'),load_eye_mapping())
        missing=[c for c in mapped['channels'] if c['rgb_status']=='MISSING_DIRECTION']
        self.assertEqual(len(missing),85)
        self.assertEqual({c['eye'] for c in missing},{'L','R'})
        self.assertTrue(all(c['rgb_code_luminance'] is None for c in missing))


@unittest.skipUnless(importlib.util.find_spec('pandas') and importlib.util.find_spec('openpyxl'),'Analysis extras required')
class LeftSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from camera_lab.biomapping import import_left_eye as src
        cls.src=src;cls.columns=pd.read_excel(src.COLUMNS);cls.angles=pd.read_excel(src.ANGLES)
        cls.inventory=json.loads(src.INVENTORY.read_text())['neurons']

    def test_exact_regeneration_independent_of_row_order(self):
        rows=self.src.build_left_mapping(self.columns.sample(frac=1,random_state=7),self.angles.sample(frac=1,random_state=3),list(reversed(self.inventory)))
        self.assertEqual(rows,load_eye_mapping('left'))

    def test_wrong_eye_ids_and_ambiguous_columns_rejected(self):
        import pandas as pd
        bad=self.columns.copy();bad.loc[0,'L2']=next(int(r['bodyId']) for r in self.inventory if r['eye']=='R')
        with self.assertRaises(ValueError):self.src.build_left_mapping(bad,self.angles,self.inventory)
        with self.assertRaises(ValueError):self.src.build_left_mapping(pd.concat([self.columns,self.columns.iloc[:1]]),self.angles,self.inventory)

    def test_angle_axes_and_hex_corruption_rejected(self):
        for key in ['hex1','y','theta']:
            bad=self.angles.copy();bad.loc[0,key]+=1
            with self.assertRaises(ValueError):self.src.validate_angles(bad)

    def test_all_author_left_directions_address_their_own_column(self):
        v=self.angles[['x','y','z']].to_numpy()
        np.testing.assert_array_equal((v@v.T).argmax(axis=1),np.arange(len(v)))

    def test_independent_csv_and_not_a_right_eye_mirror(self):
        import pandas as pd
        csv=pd.read_csv(self.src.SOURCE/f'eyemap_archive/docs/data/{self.src.DATASET}/left.csv')
        np.testing.assert_allclose(csv[['x','y','z']],self.angles[['x','y','z']],atol=5.1e-7)
        self.assertEqual(list(zip(csv.hex1,csv.hex2)),list(zip(self.angles.hex1,self.angles.hex2)))
        right=pd.read_excel(self.src.ANGLES.with_name('pqxyztp_right.xlsx'))
        both=self.angles.merge(right,on=['hex1','hex2'],suffixes=('_l','_r'))
        self.assertGreater(np.max(abs(both[['x_l','y_l','z_l']].to_numpy()-both[['x_r','y_r','z_r']].to_numpy()*[1,-1,1])),.1)


if __name__=='__main__':unittest.main()
