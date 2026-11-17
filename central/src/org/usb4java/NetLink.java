package org.usb4java;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.Properties;

/** TCP-Verbindung zum Kit Control (kitd/bridge.py). */
final class NetLink {
    static final int DEFAULT_PORT = 8766;
    static final int DISCOVERY_PORT = 8767;
    static final String USB_HOST = "10.55.0.1";

    private static boolean reachable(String host, int port, int timeoutMs) {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(host, port), timeoutMs);
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    private final Socket socket;
    private final DataInputStream in;
    private final DataOutputStream out;

    NetLink(String host, int port) throws IOException {
        socket = new Socket();
        socket.connect(new InetSocketAddress(host, port), 2000);
        socket.setTcpNoDelay(true);
        in = new DataInputStream(socket.getInputStream());
        out = new DataOutputStream(socket.getOutputStream());
    }

    /** Antwort: [0] = Status (libusb-Code), [1] = Daten. */
    synchronized Object[] call(char op, int ep, long timeoutMs, byte[] data, int len) throws IOException {
        socket.setSoTimeout((int) Math.max(3000, timeoutMs + 3000));
        out.writeByte(op);
        out.writeByte(ep);
        out.writeInt((int) timeoutMs);
        if (op == 'W') {
            out.writeInt(data.length);
            out.write(data);
        } else {
            out.writeInt(len);
        }
        out.flush();
        int status = in.readInt();
        int n = in.readInt();
        byte[] ans = new byte[n];
        in.readFully(ans);
        return new Object[] { Integer.valueOf(status), ans };
    }

    void close() {
        try { socket.close(); } catch (IOException ignored) { }
    }

    // ---------------- Wo steht der Kit Control? ----------------

    private static String cachedHost;
    private static int cachedPort = DEFAULT_PORT;
    private static long cachedAt;

    /** Reihenfolge: -Dkitcontrol.host, KITCONTROL_HOST, Datei kit-control.txt, Suche im WLAN. */
    static synchronized String[] locate() {
        String h = System.getProperty("kitcontrol.host");
        if (h == null || h.trim().isEmpty()) h = System.getenv("KITCONTROL_HOST");
        if (h == null || h.trim().isEmpty()) h = fromFile();
        if (h != null && !h.trim().isEmpty()) {
            h = h.trim();
            int port = DEFAULT_PORT;
            int c = h.lastIndexOf(':');
            if (c > 0) {
                try { port = Integer.parseInt(h.substring(c + 1)); h = h.substring(0, c); } catch (NumberFormatException ignored) { }
            }
            return new String[] { h, String.valueOf(port) };
        }
        // Pi am USB-Kabel ("PC-Verbindung: USB") hat immer diese Adresse
        if (reachable(USB_HOST, DEFAULT_PORT, 300)) {
            return new String[] { USB_HOST, String.valueOf(DEFAULT_PORT) };
        }
        if (cachedHost != null && System.currentTimeMillis() - cachedAt < 60000) {
            return new String[] { cachedHost, String.valueOf(cachedPort) };
        }
        String[] found = discover();
        if (found != null) {
            cachedHost = found[0];
            cachedPort = Integer.parseInt(found[1]);
            cachedAt = System.currentTimeMillis();
        }
        return found;
    }

    private static String fromFile() {
        String[] places = {
            System.getProperty("user.home") + File.separator + "kit-control.txt",
            new File(System.getProperty("user.dir"), "kit-control.txt").getPath()
        };
        for (String p : places) {
            File f = new File(p);
            if (!f.isFile()) continue;
            try (InputStream is = new FileInputStream(f)) {
                Properties pr = new Properties();
                pr.load(is);
                String h = pr.getProperty("host");
                if (h != null) return h;
                // auch eine Datei, die nur die Adresse enthält
                for (String k : pr.stringPropertyNames()) {
                    if (pr.getProperty(k).isEmpty()) return k;
                }
            } catch (IOException ignored) { }
        }
        return null;
    }

    private static String[] discover() {
        try (DatagramSocket s = new DatagramSocket()) {
            s.setBroadcast(true);
            s.setSoTimeout(800);
            byte[] q = "KITCONTROL?".getBytes("US-ASCII");
            s.send(new DatagramPacket(q, q.length, InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT));
            byte[] buf = new byte[256];
            DatagramPacket p = new DatagramPacket(buf, buf.length);
            s.receive(p);
            String[] parts = new String(p.getData(), 0, p.getLength(), "US-ASCII").trim().split(" ");
            if (parts.length >= 2 && parts[0].equals("KITCONTROL")) {
                return new String[] { p.getAddress().getHostAddress(), parts[1] };
            }
        } catch (IOException ignored) { }
        return null;
    }
}
