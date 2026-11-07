import android.os.BatteryManager;
import android.os.BatteryProperty;
import android.os.IBatteryPropertiesRegistrar;
import android.os.ServiceManager;
import android.os.storage.IStorageManager;

/** Read standard diagnostic properties without changing battery or storage state. */
public final class ShengHealthReadback {
    public static void main(String[] args) throws Exception {
        IBatteryPropertiesRegistrar battery = IBatteryPropertiesRegistrar.Stub.asInterface(
                ServiceManager.getService("batteryproperties"));
        if (battery == null) throw new IllegalStateException("No batteryproperties service");
        BatteryProperty soh = new BatteryProperty();
        int status = battery.getProperty(BatteryManager.BATTERY_PROPERTY_STATE_OF_HEALTH, soh);
        System.out.println("battery_soh_status=" + status);
        System.out.println("battery_soh_percent=" + soh.getLong());
        IStorageManager storage = IStorageManager.Stub.asInterface(ServiceManager.getService("mount"));
        if (storage == null) throw new IllegalStateException("No storage service");
        System.out.println("storage_remaining_lifetime_percent=" + storage.getInternalStorageRemainingLifetime());
    }
}
