import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import numpy as np
from flyvisionbridge.live_core import engineer_rates,approximate_intrinsics,BrainClient,Rectifier


class LiveEncodingTests(unittest.TestCase):
    def test_unknown_and_missing_never_generate_input(self):
        rows=[dict(bodyId='1',rgb_status='OBSERVED',rgb_code_luminance=.2),
              dict(bodyId='2',rgb_status='OUTSIDE_CAMERA_FOV',rgb_code_luminance=None),
              dict(bodyId='3',rgb_status='MISSING_DIRECTION',rgb_code_luminance=None)]
        self.assertEqual(engineer_rates({'channels':rows}),[dict(bodyId='1',rate_hz=96.)])
        rows[0]['rgb_code_luminance']=float('nan')
        with self.assertRaises(ValueError):engineer_rates({'channels':rows})

    def test_black_white_and_gain_bounds(self):
        def sample(l):return {'channels':[dict(bodyId='1',rgb_status='OBSERVED',rgb_code_luminance=l)]}
        self.assertEqual(engineer_rates(sample(1))[0]['rate_hz'],0)
        self.assertEqual(engineer_rates(sample(0))[0]['rate_hz'],120)
        self.assertEqual(engineer_rates(sample(.5),60)[0]['rate_hz'],30)
        for g in [-1,121,float('nan')]:
            with self.assertRaises(ValueError):engineer_rates(sample(.5),g)

    def test_fov_is_explicit_and_preserves_square_pixels(self):
        k=approximate_intrinsics(640,480,90)
        self.assertAlmostEqual(k['fx'],320)
        self.assertEqual(k['fx'],k['fy'])
        self.assertEqual(k['calibration_status'],'APPROXIMATE_FOV_NOT_CALIBRATED')
        with self.assertRaises(ValueError):approximate_intrinsics(640,480,180)

    @unittest.skipUnless(importlib.util.find_spec('cv2'),'OpenCV optional; full suite requires analysis extras')
    def test_rectification_border_is_unknown_not_dark(self):
        k=dict(width=20,height=20,fx=10,fy=10,ppx=10,ppy=10,coeffs=[.8,0,0,0,0])
        r=Rectifier(k)
        mapped={'channels':[dict(bodyId='1',rgb_status='OBSERVED',pixel_uv=[0.,0.],rgb_code_luminance=0.),
                            dict(bodyId='2',rgb_status='OBSERVED',pixel_uv=[10.,10.],rgb_code_luminance=.5)]}
        r.mask_channels(mapped)
        self.assertEqual(mapped['channels'][0]['rgb_status'],'INVALID_RECTIFICATION_BORDER')
        self.assertEqual(engineer_rates(mapped),[dict(bodyId='2',rate_hz=60.)])
        self.assertFalse(any(r.k['coeffs']))
        with self.assertRaises(ValueError):r.apply(np.zeros((21,20,3),np.uint8))


@unittest.skipUnless(shutil.which('node'),'Node.js required for engine protocol tests')
class PersistentBrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        (cls.root/'src').mkdir();(cls.root/'public/data').mkdir(parents=True)
        fixture=Path(__file__).parent/'fixtures/brain_cpu/brain.js'
        shutil.copyfile(fixture,cls.root/'src/brain.js')
        (cls.root/'package.json').write_text('{"type":"module"}')
        d=cls.root/'public/data'
        neurons=[['1','L2','optic','R','acetylcholine',1],['2','L2','optic','L','acetylcholine',1],['3','SyntheticDownstream','central','R','acetylcholine',1]]
        (d/'neurons.json.gz').write_bytes(gzip.compress(json.dumps(neurons).encode()))
        arrays=[]
        for name,values in [('offsets',[0,0,0,1]),('sources',[0]),('counts',[100])]:
            data=gzip.compress(np.asarray(values,dtype='<u4').tobytes());file=name+'.gz';(d/file).write_bytes(data)
            arrays.append(dict(name=name,length=len(values),parts=[dict(file=file,sha256=hashlib.sha256(data).hexdigest())]))
        (d/'manifest.json').write_text(json.dumps(dict(neurons=3,edges=1,metadata='neurons.json.gz',arrays=arrays)))
        cls.client=BrainClient(cls.root)

    @classmethod
    def tearDownClass(cls):cls.client.close();cls.temp.cleanup()

    def setUp(self):self.client.request('reset')

    def test_ticks_persist_across_frames_and_reset_is_explicit(self):
        a=self.client.request('step',channels=[dict(bodyId='1',rate_hz=120)],steps=200)
        b=self.client.request('step',channels=[dict(bodyId='1',rate_hz=120)],steps=200)
        self.assertEqual((a['tick_before'],a['tick_after'],b['tick_before'],b['tick_after']),(0,200,200,400))
        self.assertGreater(a['total_spikes']+b['total_spikes'],0)
        self.assertEqual(self.client.request('reset')['tick'],0)

    def test_zero_input_and_disconnected_controls(self):
        r=self.client.request('controls',channels=[dict(bodyId='1',rate_hz=120)],steps=1000)['runs']
        self.assertEqual(r['no_input']['total_spikes'],0)
        self.assertGreater(r['camera']['downstream_spikes'],0)
        self.assertEqual(r['connections_off']['downstream_spikes'],0)
        self.assertGreater(r['connections_off']['input_neuron_spikes'],0)
        self.assertNotEqual(r['half_gain']['total_spikes'],r['camera']['total_spikes'])

    def test_absent_channel_does_not_keep_previous_rate(self):
        self.client.request('step',channels=[dict(bodyId='1',rate_hz=120)],steps=500,connections_off=True)
        # Allow the final pending threshold crossing, then observe a quiet empty-input window.
        self.client.request('step',channels=[],steps=500,connections_off=True)
        final=self.client.request('step',channels=[],steps=500,connections_off=True)
        self.assertEqual(final['total_spikes'],0)

    def test_bad_identity_and_rate_do_not_advance_model(self):
        for channels in [[dict(bodyId='2',rate_hz=1)],[dict(bodyId='3',rate_hz=1)],
                         [dict(bodyId='1',rate_hz=121)],[dict(bodyId='1',rate_hz=1)]*2]:
            with self.assertRaises(ValueError):self.client.request('step',channels=channels,steps=10)
        valid=self.client.request('step',channels=[],steps=10)
        self.assertEqual(valid['tick_before'],0)


if __name__=='__main__':unittest.main()
