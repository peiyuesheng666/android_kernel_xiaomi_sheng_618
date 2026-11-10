// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

/** Fit-center, cardinal rotation and display-only front-camera mirroring. */
public final class PreviewGeometry {
    private PreviewGeometry() {}
    public static float[] sensor(int width, int height, int degrees, int viewWidth, int viewHeight) {
        if (width <= 0 || height <= 0 || viewWidth <= 0 || viewHeight <= 0
                || degrees < 0 || degrees >= 360 || degrees%90 != 0)
            throw new IllegalArgumentException("Invalid preview geometry");
        int cos = new int[]{1,0,-1,0}[degrees/90], sin = new int[]{0,1,0,-1}[degrees/90];
        int rw = degrees%180 == 0 ? width : height, rh = degrees%180 == 0 ? height : width;
        float scale = Math.min((float)viewWidth/rw, (float)viewHeight/rh);
        float a = -scale*cos, b = scale*sin, d = scale*sin, e = scale*cos;
        return new float[]{a,b,viewWidth/2f-a*width/2f-b*height/2f,
                d,e,viewHeight/2f-d*width/2f-e*height/2f,0,0,1};
    }
    public static float[] texture(int width, int height, int degrees, int viewWidth, int viewHeight) {
        float[] result = sensor(width,height,degrees,viewWidth,viewHeight);
        // TextureView initially stretches buffer coordinates to its own view dimensions.
        result[0] *= (float)width/viewWidth; result[3] *= (float)width/viewWidth;
        result[1] *= (float)height/viewHeight; result[4] *= (float)height/viewHeight;
        return result;
    }
}
