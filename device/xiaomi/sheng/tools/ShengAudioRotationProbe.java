import android.media.AudioSystem;
import android.os.ServiceManager;
import android.hardware.display.IDisplayManager;
import android.view.DisplayInfo;

/** Explicit, temporary HAL rotation request; never changes rotation settings. */
public final class ShengAudioRotationProbe {
    public static void main(String[] args) throws Exception {
        IDisplayManager displays = IDisplayManager.Stub.asInterface(
                ServiceManager.getService("display"));
        DisplayInfo display = displays.getDisplayInfo(0);
        int actual = display.rotation * 90;
        int degrees = args.length > 0 ? Integer.parseInt(args[0]) : actual;
        if (degrees < 0 || degrees > 270 || degrees % 90 != 0)
            throw new IllegalArgumentException("rotation must be 0/90/180/270");
        int status = AudioSystem.setParameters("rotation=" + degrees);
        System.out.println("DISPLAY=" + actual + " HAL_REQUEST=" + degrees + " STATUS=" + status);
        System.exit(status == 0 ? 0 : 1);
    }
}
