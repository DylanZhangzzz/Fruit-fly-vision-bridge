import unittest
import numpy as np
from analyze_calibrated import inverse_lookup,sine_metrics,motion_metrics,reference_correct


class CalibratedTests(unittest.TestCase):
    def test_independent_references_remove_affine_drift_without_test_targets(self):
        true=np.array([[30.,60.],[40.,75.],[20.,55.]])
        gain=np.array([1.1,.9,1.2]);offset=np.array([3.,-2.,4.])
        observed=true*gain[:,None]+offset[:,None]
        fixed,scale=reference_correct(observed,10*gain+offset,110*gain+offset,{'black_camera':10,'white_camera':110})
        np.testing.assert_allclose(fixed,true)
        bad,_=reference_correct(observed,np.zeros(3),np.full(3,15.),{'black_camera':10,'white_camera':110})
        self.assertTrue(np.isnan(bad).all())

    def test_inverse_rejects_flat_intervals_unknowns_and_extrapolation(self):
        channel=dict(gray_codes=[0,40,80,120,160],monotone_camera_values=[2,2.5,5,30,70])
        result=inverse_lookup(np.array([-1,2.2,np.nan,71,17.5,50]),channel)
        self.assertTrue(np.isnan(result[:4]).all())
        np.testing.assert_allclose(result[4:],[100,140])

    def test_sine_phase_is_free_but_wrong_amplitude_and_frequency_fail(self):
        t=np.arange(180)/60
        clean=160+48*np.sin(2*np.pi*2*t+.63)
        self.assertTrue(sine_metrics(t,clean,2)['pass_check'])
        self.assertFalse(sine_metrics(t,160+(clean-160)*.75,2)['pass_check'])
        self.assertFalse(sine_metrics(t,clean,4)['pass_check'])

    def test_motion_order_and_mirrored_mapping_negative_control(self):
        t=np.arange(180)/60;x=np.linspace(280,720,15)
        centers=(x-240)/(520/3)
        values=160-48*np.exp(-((t[:,None]-centers[None])/0.2)**8)
        good=motion_metrics(t,values,x,'move_right')
        self.assertTrue(good['pass_check']);self.assertTrue(good['mirrored_coordinates_would_fail'])
        self.assertFalse(motion_metrics(t,values,x,'move_left')['pass_check'])
        self.assertFalse(motion_metrics(t,np.full_like(values,np.nan),x,'move_right')['pass_check'])


if __name__=='__main__':unittest.main()
