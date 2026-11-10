// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import java.nio.ByteBuffer;
import java.util.Arrays;

/** Synthetic geometry, buffer ownership and frame scheduling; no camera or personal data. */
public final class PipelineTests {
    private static int checks;
    private static void check(boolean result,String detail) {
        checks++; if (!result) throw new AssertionError(detail);
    }
    private static ByteBuffer pixels(int w,int h,int step,int origin,int seed) {
        int row=w*step+3, end=origin+(h-1)*row+(w-1)*step+1;
        ByteBuffer result=ByteBuffer.allocateDirect(end+5);
        for (int y=0;y<h;y++) for (int x=0;x<w;x++) result.put(origin+y*row+x*step,(byte)(seed+y*w+x));
        result.position(origin); result.limit(end); return result.asReadOnlyBuffer();
    }
    private static FrameMath.Plane plane(ByteBuffer b,int w,int h,int step) {
        return new FrameMath.Plane(b,w*step+3,step,w,h);
    }
    private static float[] point(float[] matrix,float x,float y) {
        return new float[]{matrix[0]*x+matrix[1]*y+matrix[2],matrix[3]*x+matrix[4]*y+matrix[5]};
    }
    private static void near(double a,double b,String label) { check(Math.abs(a-b)<.0001,label); }
    public static void main(String[] args) {
        for (int yStep:new int[]{1,2}) for (int uvStep:new int[]{1,2,3}) for (int origin:new int[]{1,3}) {
            ByteBuffer y=pixels(4,4,yStep,origin,1),u=pixels(2,2,uvStep,origin,101),v=pixels(2,2,uvStep,origin,201);
            FrameMath.Plane yp=plane(y,4,4,yStep),up=plane(u,2,2,uvStep),vp=plane(v,2,2,uvStep);
            byte[] packed=FrameMath.nv21(yp,up,vp);
            byte[] reference=new byte[24];
            for (int row=0;row<4;row++) for (int col=0;col<4;col++) reference[row*4+col]=(byte)yp.at(col,row);
            for (int row=0;row<2;row++) for (int col=0;col<2;col++) {
                reference[16+row*4+col*2]=(byte)vp.at(col,row);
                reference[17+row*4+col*2]=(byte)up.at(col,row);
            }
            check(Arrays.equals(packed,reference),"NV21 matches individual samples across offsets/strides");
            check(y.position()==origin && u.position()==origin && v.position()==origin,"Source buffers untouched");
        }
        boolean rejected=false;
        try { FrameMath.nv21(plane(pixels(4,4,1,0,0),4,4,1),
                plane(pixels(1,2,1,0,0),1,2,1),plane(pixels(2,2,1,0,0),2,2,1)); }
        catch (IllegalArgumentException expected) { rejected=true; }
        check(rejected,"Incompatible chroma geometry rejected");

        AnalysisGate gate=new AnalysisGate(100);
        check(!gate.acquire(-1),"Negative timestamp rejected");
        check(gate.acquire(1000),"First ownership acquired");
        check(!gate.acquire(2000),"Second inference never queued while busy");
        gate.resetTiming(); check(!gate.acquire(0),"Cancel/reset preserves in-flight ownership");
        gate.release(); check(gate.acquire(0),"New camera timestamp accepted after owner releases");
        gate.release(); check(!gate.acquire(99),"Too-close analysis skipped");
        check(gate.acquire(100),"Interval boundary admitted"); gate.release();

        SampleCollector collector=new SampleCollector(FaceEmbedding::validate);
        float[] raw=new float[128]; Arrays.fill(raw,1); float[] embedding=FaceEmbedding.normalized(raw);
        check(!collector.wantsSample(0),"No inference needed before enrollment");
        long generation=collector.begin();
        check(collector.wantsSample(0) && !collector.wantsSample(-1),"First valid sample requested");
        check(collector.offer(generation,0,embedding),"First embedding admitted");
        check(!collector.wantsSample(SampleCollector.INTERVAL_NS-1),"Duplicate feature computation skipped");
        check(collector.wantsSample(SampleCollector.INTERVAL_NS),"Next valid sample requested");
        collector.cancel(); check(!collector.wantsSample(Long.MAX_VALUE),"Canceled collection needs no features");

        for (int angle:new int[]{0,90,180,270}) for (int vw:new int[]{8,12}) {
            float[] sensor=PreviewGeometry.sensor(4,2,angle,vw,8), texture=PreviewGeometry.texture(4,2,angle,vw,8);
            float[] center=point(sensor,2,1); near(center[0],vw/2.0,"Centered X"); near(center[1],4,"Centered Y");
            check(sensor[0]*sensor[4]-sensor[1]*sensor[3]<0,"Only displayed image is mirrored");
            float[] a=point(sensor,3.1f,.7f),b=point(texture,3.1f*vw/4,.7f*8/2);
            near(a[0],b[0],"Texture stretch undone X"); near(a[1],b[1],"Texture stretch undone Y");
            for (int x:new int[]{0,4}) for (int y:new int[]{0,2}) {
                float[] p=point(sensor,x,y);
                check(p[0]>=-.0001 && p[0]<=vw+.0001 && p[1]>=-.0001 && p[1]<=8.0001,"All sensor edges remain visible");
            }
        }
        System.out.println("PASS "+checks+" pipeline checks");
    }
}
