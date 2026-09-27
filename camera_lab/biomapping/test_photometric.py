import unittest
import numpy as np
from analyze_photometric import gray_decode, decode_dualrail, monotone_fit, stable_indices, fit_channel


class PhotometricTests(unittest.TestCase):
    @staticmethod
    def entries():
        train=np.round(np.arange(32)*255/31).astype(int)
        holdout=np.round((train[::2]+train[1::2])/2).astype(int)
        response=lambda x: 12+180*(x/255)**1.8
        return [dict(kind=kind,level=int(x),samples=22,median=response(x))
                for kind,levels in [('train',train),('holdout',holdout),
                                    ('repeat',train[[0,8,16,24,31,8,16,24]])]
                for x in levels]

    def test_all_gray_codes_round_trip_and_adjacent_one_bit(self):
        codes=[i^(i>>1) for i in range(256)]
        self.assertEqual([gray_decode(c) for c in codes],list(range(256)))
        self.assertTrue(all((a^b).bit_count()==1 for a,b in zip(codes,codes[1:])))

    def test_monotone_pooling_weighted(self):
        np.testing.assert_allclose(monotone_fit([0,4,2,6],[1,1,3,1]),[0,2.5,2.5,6])

    def test_local_phase_pairs_and_uncertain_bit_rejection(self):
        for phase in range(58):
            im=np.zeros((700,1000));code=phase^(phase>>1)
            for i in range(8):
                x=240+65*i;lo=3+i*5;hi=100+i*9;bit=(code>>i)&1
                im[565:605,x:x+27]=hi if bit else lo
                im[565:605,x+33:x+60]=lo if bit else hi
            self.assertEqual(decode_dualrail(im,set(range(58)))[0],phase)
            im[565:605,240:300]=50
            self.assertEqual(decode_dualrail(im,set(range(58)))[0],-1)

    def test_transition_trim_does_not_join_disconnected_segments(self):
        labels=np.array([7]*6+[-1]+[7]*20+[-1])
        np.testing.assert_array_equal(stable_indices(labels,7),np.arange(11,23))
        self.assertEqual(len(stable_indices(labels,99)),0)

    def test_withheld_levels_validate_without_changing_training(self):
        entries=self.entries();good=fit_channel(entries)
        self.assertEqual(good['status'],'PASS_ENGINEERING_TRANSFER')
        for e in entries:
            if e['kind']=='holdout':e['median']+=20
        bad=fit_channel(entries)
        self.assertEqual(bad['status'],'FAIL_OR_INCOMPLETE_TRANSFER')
        self.assertEqual(good['monotone_camera_values'],bad['monotone_camera_values'])

    def test_drift_and_missing_training_rejected(self):
        entries=self.entries()
        for e in entries:
            if e['kind']=='repeat':e['median']+=20
        self.assertEqual(fit_channel(entries)['status'],'FAIL_OR_INCOMPLETE_TRANSFER')
        entries[0]['samples']=11
        self.assertEqual(fit_channel(entries)['status'],'INSUFFICIENT_TRAINING_LEVELS')

    def test_low_dynamic_range_rejected(self):
        entries=self.entries()
        for e in entries:e['median']=25+e['median']/100
        self.assertEqual(fit_channel(entries)['status'],'INSUFFICIENT_CAMERA_RANGE')


if __name__=='__main__':unittest.main()
