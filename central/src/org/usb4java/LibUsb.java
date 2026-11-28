package org.usb4java;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.IntBuffer;

/**
 * Ersatz für usb4java, nur mit den Funktionen, die Sintratec Central nutzt.
 * Statt über USB laufen alle Transfers über das WLAN zum Kit Control (Raspberry Pi am Kit).
 */
public final class LibUsb {
    private LibUsb() {}

    // libusb-Rückgabewerte
    public static final int SUCCESS = 0;
    public static final int ERROR_IO = -1;
    public static final int ERROR_INVALID_PARAM = -2;
    public static final int ERROR_ACCESS = -3;
    public static final int ERROR_NO_DEVICE = -4;
    public static final int ERROR_NOT_FOUND = -5;
    public static final int ERROR_BUSY = -6;
    public static final int ERROR_TIMEOUT = -7;
    public static final int ERROR_OVERFLOW = -8;
    public static final int ERROR_PIPE = -9;
    public static final int ERROR_INTERRUPTED = -10;
    public static final int ERROR_NO_MEM = -11;
    public static final int ERROR_NOT_SUPPORTED = -12;
    public static final int ERROR_OTHER = -99;

    public static final int CAP_HAS_CAPABILITY = 0x0000;
    public static final int CAP_HAS_HOTPLUG = 0x0001;
    public static final int CAP_HAS_HID_ACCESS = 0x0100;
    public static final int CAP_SUPPORTS_DETACH_KERNEL_DRIVER = 0x0101;

    static final short KIT_VENDOR = (short) 0x03EB;
    static final short KIT_PRODUCT = (short) 0x8002;

    public static int init(Context context) { return SUCCESS; }

    public static void exit(Context context) { }

    public static boolean hasCapability(int capability) {
        return capability == CAP_HAS_CAPABILITY;
    }

    public static int getDeviceList(Context context, DeviceList list) {
        list.devices.clear();
        String[] where = NetLink.locate();
        if (where == null) return 0;
        String host = where[0];
        int port = Integer.parseInt(where[1]);
        NetLink probe = null;
        try {
            probe = new NetLink(host, port);
            // Erst anmelden (gekoppelt?), sonst zeigt der Pi keinen Kit – die Kopplung läuft dann im Hintergrund an
            if (!Pairing.authenticate(probe, host, port)) return 0;
            int status = ((Integer) probe.call('H', 0, 1000, null, 0)[0]).intValue();
            if (status == SUCCESS) list.devices.add(new Device(host, port));
        } catch (IOException ignored) {
            // Kit Control nicht erreichbar: keine Geräte
        } finally {
            if (probe != null) probe.close();
        }
        return list.devices.size();
    }

    public static void freeDeviceList(DeviceList list, boolean unrefDevices) { }

    public static int getDeviceDescriptor(Device device, DeviceDescriptor descriptor) {
        descriptor.vendor = KIT_VENDOR;
        descriptor.product = KIT_PRODUCT;
        return SUCCESS;
    }

    public static int open(Device device, DeviceHandle handle) {
        if (device == null || device.host == null) return ERROR_NO_DEVICE;
        NetLink link = null;
        try {
            link = new NetLink(device.host, device.port);
            if (!Pairing.authenticate(link, device.host, device.port)) {
                link.close();
                return ERROR_ACCESS;
            }
            handle.link = link;
            return SUCCESS;
        } catch (IOException e) {
            if (link != null) link.close();
            return ERROR_NO_DEVICE;
        }
    }

    public static void close(DeviceHandle handle) {
        if (handle != null && handle.link != null) {
            handle.link.close();
            handle.link = null;
        }
    }

    public static int kernelDriverActive(DeviceHandle handle, int iface) { return 0; }

    public static int detachKernelDriver(DeviceHandle handle, int iface) { return SUCCESS; }

    public static int attachKernelDriver(DeviceHandle handle, int iface) { return SUCCESS; }

    public static int claimInterface(DeviceHandle handle, int iface) {
        return handle != null && handle.link != null ? SUCCESS : ERROR_NO_DEVICE;
    }

    public static int releaseInterface(DeviceHandle handle, int iface) { return SUCCESS; }

    public static int setInterfaceAltSetting(DeviceHandle handle, int iface, int alt) { return SUCCESS; }

    public static int bulkTransfer(DeviceHandle handle, byte endpoint, ByteBuffer data, IntBuffer transferred, long timeout) {
        if (handle == null || handle.link == null) return ERROR_NO_DEVICE;
        boolean in = (endpoint & 0x80) != 0;
        int capacity = data.capacity();
        try {
            if (!in) {
                byte[] bytes = new byte[capacity];
                for (int i = 0; i < capacity; i++) bytes[i] = data.get(i);
                Object[] r = handle.link.call('W', endpoint & 0xFF, timeout, bytes, 0);
                int status = ((Integer) r[0]).intValue();
                if (status == SUCCESS) transferred.put(0, capacity);
                return status;
            }
            Object[] r = handle.link.call('R', endpoint & 0xFF, timeout, null, capacity);
            int status = ((Integer) r[0]).intValue();
            byte[] ans = (byte[]) r[1];
            int n = Math.min(ans.length, capacity);
            for (int i = 0; i < n; i++) data.put(i, ans[i]);
            transferred.put(0, n);
            return status;
        } catch (IOException e) {
            close(handle);
            return ERROR_NO_DEVICE;
        }
    }
}
