"""Scientific invariants for held-out physiology analysis."""
import unittest
import numpy as np
from validate_l2_cells import binned_response, training_fold, metrics, BIN_WIDTH


class PhysiologyTests(unittest.TestCase):
    def test_feedback_free_matches_analytic_bin_integral(self):
        t=np.arange(63)*BIN_WIDTH
        tv,delay,duration=.019,.017,.02
        p=[tv,.4,0,.3,4,2,.1,delay]
        def area(t):
            x=np.maximum(t-delay,0)
            d=np.minimum(x,duration)
            return d-tv*(-np.expm1(-d/tv))+tv*(-np.expm1(-duration/tv))*(-np.expm1(-np.maximum(x-duration,0)/tv))
        expected=(area(t)-area(t-BIN_WIDTH))/BIN_WIDTH
        expected=np.array([-2*expected,4*expected])+.1
        np.testing.assert_allclose(binned_response(p,t,False),expected,atol=4e-6,rtol=4e-6)

    def test_no_response_before_latency(self):
        t=np.arange(63)*BIN_WIDTH
        p=[.02,.4,8,.3,4,2,.15,.025]
        np.testing.assert_allclose(binned_response(p,t)[:,t<=.025],.15,atol=1e-12)

    def test_test_fly_cannot_change_training_scale_or_waveform(self):
        records=[dict(flyID=f,author_selected=True,rats=np.ones((2,63))*f)
                 for f in [1,1,2,3]]
        ids,first=training_fold(records,1)
        for r in records:
            if r['flyID']==1:r['rats'][:]=1e9
        ids2,second=training_fold(records,1)
        self.assertEqual(ids,[2,3]);self.assertEqual(ids,ids2)
        np.testing.assert_array_equal(first,second)

    def test_each_fly_has_equal_weight_despite_roi_count(self):
        records=[dict(flyID=f,author_selected=True,rats=np.ones((2,63))*f)
                 for f in [1]*20+[2,3]]
        _,train=training_fold(records,3)
        self.assertEqual(train.mean(),1.5)

    def test_high_correlation_does_not_hide_wrong_amplitude(self):
        a=np.arange(10,dtype=float)
        m=metrics(a,10*a)
        self.assertAlmostEqual(m['correlation'],1)
        self.assertLess(m['r2'],0)

    def test_solver_accuracy_does_not_dominate_response(self):
        t=np.arange(63)*BIN_WIDTH;p=[.013,.56,13,.17,5,3,.0,.0167]
        np.testing.assert_allclose(binned_response(p,t),binned_response(p,t,rtol=2e-9),atol=4e-5,rtol=1e-4)


if __name__=='__main__':unittest.main()
