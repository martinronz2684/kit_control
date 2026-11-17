package org.usb4java;

/** Ein Kit Control im Netz, der sich Central gegenüber als Sintratec Kit ausgibt. */
public final class Device {
    final String host;
    final int port;

    public Device() { this(null, 0); }

    Device(String host, int port) {
        this.host = host;
        this.port = port;
    }

    @Override
    public String toString() { return "Kit Control " + host + ":" + port; }
}
