package org.usb4java;

public final class DeviceDescriptor {
    short vendor;
    short product;

    public DeviceDescriptor() {}

    public short idVendor() { return vendor; }

    public short idProduct() { return product; }
}
