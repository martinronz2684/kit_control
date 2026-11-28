package org.usb4java;

import java.awt.GridLayout;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigInteger;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import javax.swing.JDialog;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

/**
 * Kopplung von Central mit dem Kit Control am Pi (gleiches Verfahren wie die PC-App, kitctl/auth.py).
 * Beim ersten Verbinden erscheint am Kit-Display ein 6-stelliger Code; Central fragt ihn in einem Fenster ab.
 * Danach meldet sich jede Verbindung mit HMAC über eine Einmalnummer des Pi an. Der Schlüssel liegt in
 * %APPDATA%\KitControl\central-pairing.properties und geht nie über das Netz.
 */
final class Pairing {
    private Pairing() {}

    static final BigInteger P = new BigInteger(
        "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
        + "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
        + "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
        + "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
        + "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
        + "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16);
    static final BigInteger G = BigInteger.valueOf(2);
    private static final SecureRandom RNG = new SecureRandom();

    private static volatile boolean running;
    private static volatile boolean declined;          // „Abbrechen“ gedrückt: bis Central neu startet nicht mehr fragen
    private static volatile long quietUntil;           // nach einem Fehler eine Weile nicht erneut fragen
    private static volatile boolean warned;            // Hinweis „gerade nicht möglich“ schon gezeigt

    // ---------------- Anmelden ----------------

    /** Meldet die Verbindung an. false: nicht gekoppelt (dann läuft im Hintergrund die Kopplung an). */
    static boolean authenticate(NetLink link, String host, int port) throws IOException {
        String[] info = link.json('I', "{}");
        if (code(info) != LibUsb.SUCCESS) return false;
        String dev = str(info[1], "device_id");
        String[] cred = load(dev);
        if (cred == null) {
            pairAsync(host, port);
            return false;
        }
        String[] n = link.json('N', "{}");
        if (code(n) != LibUsb.SUCCESS) return false;
        String nonce = str(n[1], "nonce");
        String[] a = link.json('A', "{\"client_id\":\"" + cred[0] + "\",\"mac\":\"" + mac(unhex(cred[1]), "bridge", nonce) + "\"}");
        if (code(a) == LibUsb.SUCCESS) return true;
        // Der Kit kennt diese Kopplung nicht mehr (am Display entfernt): vergessen und neu koppeln
        forget(dev);
        pairAsync(host, port);
        return false;
    }

    private static int code(String[] r) { return Integer.parseInt(r[0]); }

    // ---------------- Koppeln ----------------

    static synchronized void pairAsync(final String host, final int port) {
        if (running || declined || System.currentTimeMillis() < quietUntil) return;
        running = true;
        Thread t = new Thread(new Runnable() {
            public void run() {
                try { pair(host, port); } finally { running = false; }
            }
        }, "kitcontrol-pairing");
        t.setDaemon(true);
        t.start();
    }

    private static void pair(String host, int port) {
        NetLink link = null;
        try {
            link = new NetLink(host, port);
            BigInteger a = new BigInteger(256, RNG).setBit(255);
            BigInteger A = G.modPow(a, P);
            String[] r = link.json('P', "{\"name\":\"" + esc(name()) + "\",\"A\":\"" + A.toString(16) + "\"}");
            if (code(r) != LibUsb.SUCCESS) {
                // z. B. Kit druckt oder heizt vor: Hinweis nur einmal je Central-Sitzung, dann still alle 2 min neu versuchen
                quietUntil = System.currentTimeMillis() + 120000;
                if (!warned) {
                    warned = true;
                    message("Central kann sich gerade nicht mit dem Kit koppeln:\n\n" + str(r[1], "error")
                        + "\n\nCentral fragt später von selbst noch einmal.", JOptionPane.WARNING_MESSAGE);
                }
                return;
            }
            String reqId = str(r[1], "request_id");
            String dev = str(r[1], "device_id");
            BigInteger B = new BigInteger(str(r[1], "B"), 16);
            BigInteger shared = B.modPow(a, P);
            String hint = "";
            while (true) {
                String code = askCode(hint);
                if (code == null) { declined = true; return; }
                byte[] key = derive(code, A, B, shared);
                String[] c = link.json('C', "{\"request_id\":\"" + reqId + "\",\"mac\":\"" + mac(key, "client", reqId) + "\"}");
                if (code(c) == LibUsb.SUCCESS) {
                    String cid = str(c[1], "client_id");
                    if (!mac(key, "server", cid).equals(str(c[1], "mac"))) {
                        message("Der Kit hat sich nicht ausgewiesen – Kopplung verworfen.", JOptionPane.ERROR_MESSAGE);
                        return;
                    }
                    save(dev, cid, hex(key));
                    message("Central ist jetzt mit dem Kit gekoppelt.\nDer Kit erscheint gleich in der Geräteliste.", JOptionPane.INFORMATION_MESSAGE);
                    return;
                }
                String err = str(c[1], "error");
                if (err.startsWith("Code falsch")) { hint = err; continue; }
                quietUntil = System.currentTimeMillis() + 60000;
                message("Kopplung fehlgeschlagen:\n\n" + err, JOptionPane.WARNING_MESSAGE);
                return;
            }
        } catch (Exception e) {
            quietUntil = System.currentTimeMillis() + 30000;
        } finally {
            if (link != null) link.close();
        }
    }

    private static String name() {
        String n = System.getenv("COMPUTERNAME");
        if (n == null || n.isEmpty()) {
            try { n = InetAddress.getLocalHost().getHostName(); } catch (IOException e) { n = "PC"; }
        }
        return "Central (" + n + ")";
    }

    // ---------------- Fenster ----------------

    private static String askCode(final String hint) {
        final String[] out = new String[1];
        run(new Runnable() {
            public void run() {
                JTextField field = new JTextField(8);
                field.setFont(field.getFont().deriveFont(26f));
                field.setHorizontalAlignment(JTextField.CENTER);
                JPanel p = new JPanel(new GridLayout(0, 1, 0, 8));
                p.add(new JLabel("<html><b>Central mit dem Kit koppeln</b><br><br>"
                    + "Damit nicht jeder im Netzwerk den Kit bedienen kann, koppelt sich Central einmal mit ihm.<br>"
                    + "Am Kit-Display steht jetzt ein 6-stelliger Code – bitte hier eingeben."
                    + (hint.isEmpty() ? "" : "<br><br><font color='#c9353a'>" + hint + "</font>") + "</html>"));
                p.add(field);
                JOptionPane pane = new JOptionPane(p, JOptionPane.QUESTION_MESSAGE, JOptionPane.OK_CANCEL_OPTION);
                JDialog d = pane.createDialog(null, "Kit Control – Kopplung");
                d.setAlwaysOnTop(true);
                d.addWindowFocusListener(new java.awt.event.WindowAdapter() {
                    public void windowGainedFocus(java.awt.event.WindowEvent e) { field.requestFocusInWindow(); }
                });
                d.setVisible(true);
                Object v = pane.getValue();
                if (v instanceof Integer && ((Integer) v).intValue() == JOptionPane.OK_OPTION) {
                    out[0] = field.getText().replaceAll("[^0-9]", "");
                }
                d.dispose();
            }
        });
        return out[0];
    }

    private static void message(final String text, final int type) {
        run(new Runnable() {
            public void run() {
                JOptionPane pane = new JOptionPane(text, type);
                JDialog d = pane.createDialog(null, "Kit Control");
                d.setAlwaysOnTop(true);
                d.setVisible(true);
                d.dispose();
            }
        });
    }

    private static void run(Runnable r) {
        try {
            if (SwingUtilities.isEventDispatchThread()) r.run();
            else SwingUtilities.invokeAndWait(r);
        } catch (Exception ignored) { }
    }

    // ---------------- Krypto ----------------

    static byte[] i2b(BigInteger x) {
        byte[] b = x.toByteArray(), out = new byte[256];
        int n = Math.min(b.length, 256);
        System.arraycopy(b, b.length - n, out, 256 - n, n);
        return out;
    }

    static byte[] hmac(byte[] key, byte[] msg) {
        try {
            Mac m = Mac.getInstance("HmacSHA256");
            m.init(new SecretKeySpec(key.length == 0 ? new byte[1] : key, "HmacSHA256"));
            return m.doFinal(msg);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    static byte[] derive(String code, BigInteger A, BigInteger B, BigInteger shared) {
        byte[] head = "kitpair1".getBytes(StandardCharsets.US_ASCII);
        byte[] msg = new byte[head.length + 3 * 256];
        System.arraycopy(head, 0, msg, 0, head.length);
        System.arraycopy(i2b(A), 0, msg, head.length, 256);
        System.arraycopy(i2b(B), 0, msg, head.length + 256, 256);
        System.arraycopy(i2b(shared), 0, msg, head.length + 512, 256);
        return hmac(code.getBytes(StandardCharsets.US_ASCII), msg);
    }

    static String mac(byte[] key, String label, String text) {
        return hex(hmac(key, (label + "|" + text).getBytes(StandardCharsets.UTF_8)));
    }

    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x & 0xff));
        return s.toString();
    }

    static byte[] unhex(String h) {
        byte[] b = new byte[h.length() / 2];
        for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return b;
    }

    // ---------------- JSON (nur flache Zeichenketten) ----------------

    static String str(String json, String key) {
        Matcher m = Pattern.compile("\"" + Pattern.quote(key) + "\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").matcher(json == null ? "" : json);
        if (!m.find()) return "";
        String s = m.group(1);
        StringBuilder o = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 1 < s.length()) {
                char e = s.charAt(++i);
                if (e == 'u' && i + 4 < s.length()) { o.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16)); i += 4; }
                else if (e == 'n') o.append('\n');
                else if (e == 't') o.append('\t');
                else o.append(e);
            } else {
                o.append(c);
            }
        }
        return o.toString();
    }

    static String esc(String s) {
        StringBuilder o = new StringBuilder();
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') o.append('\\').append(c);
            else if (c < 0x20 || c > 0x7e) o.append(String.format("\\u%04x", (int) c));
            else o.append(c);
        }
        return o.toString();
    }

    // ---------------- Speicher ----------------

    private static File file() {
        String base = System.getenv("APPDATA");
        File dir = base != null && !base.isEmpty() ? new File(base, "KitControl") : new File(System.getProperty("user.home"), ".kitcontrol");
        return new File(dir, "central-pairing.properties");
    }

    private static synchronized Properties props() {
        Properties p = new Properties();
        File f = file();
        if (f.isFile()) {
            try (InputStream is = new FileInputStream(f)) { p.load(is); } catch (IOException ignored) { }
        }
        return p;
    }

    private static synchronized void store(Properties p) {
        File f = file();
        f.getParentFile().mkdirs();
        try (OutputStream os = new FileOutputStream(f)) {
            p.store(os, "Kit Control - Kopplung von Central mit dem Kit (nicht weitergeben)");
        } catch (IOException ignored) { }
    }

    static String[] load(String dev) {
        Properties p = props();
        String c = p.getProperty(dev + ".client"), k = p.getProperty(dev + ".key");
        return c != null && k != null ? new String[] { c, k } : null;
    }

    static void save(String dev, String client, String key) {
        Properties p = props();
        p.setProperty(dev + ".client", client);
        p.setProperty(dev + ".key", key);
        store(p);
    }

    static void forget(String dev) {
        Properties p = props();
        p.remove(dev + ".client");
        p.remove(dev + ".key");
        store(p);
    }
}
