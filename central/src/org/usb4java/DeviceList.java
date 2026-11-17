package org.usb4java;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class DeviceList implements Iterable<Device> {
    final List<Device> devices = new ArrayList<Device>();

    public DeviceList() {}

    public int getSize() { return devices.size(); }

    public Device get(int i) { return devices.get(i); }

    @Override
    public Iterator<Device> iterator() { return devices.iterator(); }
}
