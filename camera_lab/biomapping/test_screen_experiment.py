import unittest
import cv2
import numpy as np
from analyze_screen import screen_transform,recurrent_prediction,CENTERS

class ScreenTests(unittest.TestCase):
    def test_marker_perspective_recovery(self):
        canvas=np.full((700,1000),128,np.uint8)
        dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for i,(x,y) in enumerate(CENTERS.astype(int)):
            canvas[y-47:y+47,x-47:x+47]=255
            canvas[y-35:y+35,x-35:x+35]=cv2.aruco.generateImageMarker(dictionary,i,70)
        quad=np.array([[70,60],[575,25],[565,430],[50,405]],np.float32)
        ideal=np.array([[0,0],[999,0],[999,699],[0,699]],np.float32)
        forward=cv2.getPerspectiveTransform(ideal,quad)
        image=cv2.warpPerspective(canvas,forward,(640,480))
        inverse,n=screen_transform(image)
        self.assertEqual(n,4);self.assertIsNotNone(inverse)
        points=np.array([[[300.,300.],[500,350],[700,450]]],np.float32)
        recovered=cv2.perspectiveTransform(cv2.perspectiveTransform(points,forward),inverse)
        self.assertLess(float(np.max(abs(recovered-points))),3)

    def test_no_markers_rejected(self):
        H,n=screen_transform(np.zeros((480,640),np.uint8))
        self.assertIsNone(H);self.assertEqual(n,0)

    def test_causal_hold_and_polarity(self):
        t=np.arange(60)/60;c=np.zeros((60,2));c[20:30]=[-.5,.5]
        v=recurrent_prediction(t,c)
        np.testing.assert_allclose(v[:21],0)
        self.assertGreater(v[21,0],0);self.assertLess(v[21,1],0)
        altered=c.copy();altered[40:]=1
        np.testing.assert_allclose(recurrent_prediction(t,altered)[:41],v[:41])

    def test_unknown_not_black(self):
        t=np.arange(10)/60;c=np.zeros((10,2));c[:,1]=np.nan
        v=recurrent_prediction(t,c)
        self.assertTrue(np.isnan(v[1:,1]).all());np.testing.assert_allclose(v[:,0],0)

if __name__=='__main__':unittest.main()
