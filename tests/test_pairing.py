"""Kopplung: PC-App (kitslice.net) und Central-Brücke gegen den echten HTTP-Server von kitd."""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

os.environ.setdefault("KIT_STATE_DIR", tempfile.mkdtemp(prefix="kitd-test-"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))

from http.server import ThreadingHTTPServer  # noqa: E402

from kitctl import auth as A  # noqa: E402
from kitd import bridge, server  # noqa: E402
from kitslice import net  # noqa: E402


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class PairingHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["KIT_LOOPBACK_TRUSTED"] = "0"      # der Test spricht über 127.0.0.1 wie ein Gerät im Netz
        cls.port = _free_port()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", cls.port), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        os.environ.pop("KIT_LOOPBACK_TRUSTED", None)

    def setUp(self):
        server.PAIR.req = None
        server.PAIR.cooldown.clear()
        net.AUTH.clear()
        server.WORKER._set(printing=False, state=1, transfer=None)
        server.WORKER.pending = None
        self.pi = net.Pi("127.0.0.1", self.port, timeout=5)

    def _pair(self):
        hello = self.pi.hello()
        self.assertFalse(hello["paired"])
        r = self.pi.pair_start("Werkstatt-PC")
        code = server.PAIR.pending()["code"]
        self.assertEqual(len(code), 6)
        self.assertEqual(r["device_id"], hello["device_id"])
        p = self.pi.pair_confirm(code)
        net.set_auth("127.0.0.1", p)
        return p

    def test_unpaired_is_refused_everywhere(self):
        with self.assertRaises(net.NotPaired):
            self.pi.state()
        with self.assertRaises(net.NotPaired):
            self.pi.jobs()
        with self.assertRaises(net.NotPaired):
            next(self.pi.events())
        self.assertTrue(self.pi.cmd({"cmd": "warmup", "on": True}).get("pair_required"))
        self.assertTrue(self.pi.send_job(b"x" * 600, "x").get("pair_required"))

    def test_pair_and_use(self):
        p = self._pair()
        self.assertTrue(self.pi.hello()["paired"])
        st = self.pi.state()
        self.assertNotIn("pair", st)                       # Code nie ins Netz
        self.assertIn("jobs", self.pi.jobs())
        ev = next(self.pi.events())
        self.assertIsInstance(ev, dict)
        # Unterschrift in der Adresse (EventSource im Handy-Browser, kitauth.js) – auch für Pfade mit Abfrage
        a = net.AUTH["127.0.0.1"]
        for path in ("/api/events", "/api/jobs/x/layer/1", "/api/state?x=1"):
            ts, nonce = str(int(time.time())), A.new_nonce()
            sig = A.sign(bytes.fromhex(a["key"]), "GET", path, ts, nonce, A.body_hash(b""))
            url = f"http://127.0.0.1:{self.port}{path}{'&' if '?' in path else '?'}kc={a['client_id']}&kt={ts}&kn={nonce}&ks={sig}"
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    self.assertIn(r.status, (200,), path)
                    if path == "/api/events":
                        self.assertTrue(r.readline().startswith(b"data: "))
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404, path)              # Job x gibt es nicht – aber nicht 401
        from kitctl import pjob
        data = pjob.build([[("contour", [(0, 0), (5, 0), (5, 5)])]], 0.1)
        r = self.pi.send_job(data, "Gekoppelt ä", {"name": "PA12"}, start=False)   # X-Job-* mit unterschrieben
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.pi.delete_job(r["job"]["id"])["ok"])
        comp = self.pi.compensation()
        self.assertFalse(comp["active"])
        r = self.pi.set_compensation({"scale_x_pct": 0.2, "skew_deg": -0.05})
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.pi.compensation()["active"])
        self.assertFalse(self.pi.set_compensation({"scale_x_pct": 9})["ok"])      # außerhalb ±5 %
        self.pi.set_compensation({})
        names = [c["name"] for c in server.PAIR.clients()]
        self.assertIn("Werkstatt-PC", names)
        # Kopplung entfernen (nur am Display) -> wieder abgewiesen
        server.PAIR.remove(p["client_id"])
        with self.assertRaises(net.NotPaired):
            self.pi.state()

    def test_wrong_code_and_lockout(self):
        self.pi.pair_start("PC")
        code = server.PAIR.pending()["code"]
        wrong = f"{(int(code) + 1) % 1000000:06d}"
        for i in range(A.CODE_DIGITS - 2):
            with self.assertRaises(net.PairFailed) as cm:
                self.pi.pair_confirm(wrong)
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(net.PairFailed) as cm:
            self.pi.pair_confirm(wrong)                    # 5. Versuch: Anfrage verfällt
        self.assertEqual(cm.exception.status, 429)
        self.assertIsNone(server.PAIR.pending())
        with self.assertRaises(net.PairFailed):
            self.pi.pair_confirm(code)                     # richtiger Code hilft jetzt nicht mehr
        with self.assertRaises(net.PairFailed):
            self.pi.pair_start("PC")                       # eine Minute gesperrt

    def test_refused_while_busy(self):
        for kw, word in (({"printing": True, "state": 8}, "druckt"), ({"state": 5}, "heizt"),
                         ({"state": 4}, "Pulver"), ({"transfer": {"id": "x"}}, "übertragen")):
            server.WORKER._set(printing=False, state=1, transfer=None)
            server.WORKER._set(**kw)
            with self.assertRaises(net.PairFailed) as cm:
                self.pi.pair_start("PC")
            self.assertIn(word, str(cm.exception))
        server.WORKER._set(printing=False, state=1, transfer=None)
        self.pi.pair_start("PC")
        code = server.PAIR.pending()["code"]
        server.WORKER._set(state=5)                         # Vorheizen beginnt, während jemand tippt
        with self.assertRaises(net.PairFailed):
            self.pi.pair_confirm(code)
        self.assertIsNone(server.PAIR.req)

    def test_replay_and_tamper_refused(self):
        self._pair()
        req = self.pi._request("GET", "/api/state")
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as cm:   # dieselbe Anfrage noch einmal
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 401)
        body = json.dumps({"cmd": "warmup", "on": True}).encode()
        req = self.pi._request("POST", "/api/cmd", body, {"Content-Type": "application/json"})
        req.data = json.dumps({"cmd": "warmup", "on": False}).encode()   # Rumpf verändert
        req.add_header("Content-Length", str(len(req.data)))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 401)
        # Uhr des Geräts weit daneben -> abgewiesen; nach /api/pair/hello wieder gut
        net.OFFSET["127.0.0.1"] = -3600
        with self.assertRaises(net.NotPaired):
            self.pi.state()
        self.pi.hello()
        self.pi.state()

    def test_display_reject_blocks_peer(self):
        self.pi.pair_start("PC")
        self.assertTrue(server.PAIR.cancel())
        with self.assertRaises(net.PairFailed) as cm:
            self.pi.pair_start("PC")
        self.assertIn("gesperrt", str(cm.exception))


class _BridgeClient:
    """Verhält sich wie die Central-Bibliothek (central/src/org/usb4java/NetLink.java)."""

    def __init__(self, port):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=5)

    def call(self, op, payload=b"", ep=0, timeout=1000, rlen=0):
        if op == "R":
            self.s.sendall(struct.pack(">cBII", b"R", ep, timeout, rlen))
        else:
            self.s.sendall(struct.pack(">cBII", op.encode(), ep, timeout, len(payload)) + payload)
        head = self._recv(8)
        status, n = struct.unpack(">iI", head)
        return status, self._recv(n)

    def j(self, op, obj):
        st, data = self.call(op, json.dumps(obj).encode())
        return st, (json.loads(data) if data else {})

    def _recv(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise ConnectionError
            b += c
        return b

    def close(self):
        self.s.close()


class PairingBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        bridge.PORT = cls.port

        class W:
            kit = None
            usb = threading.RLock()

            @staticmethod
            def snapshot():
                return {}
        srv = bridge._Server(("127.0.0.1", cls.port), bridge.Session)
        bridge.Session.worker = W
        bridge.Session.pairing = server.PAIR
        bridge.Session.busy = staticmethod(lambda: "")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.srv = srv

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        server.PAIR.req = None
        server.PAIR.cooldown.clear()

    def test_old_library_is_refused(self):
        c = _BridgeClient(self.port)
        st, _ = c.call("H")
        self.assertEqual(st, bridge.ERR_ACCESS)
        c.close()

    def test_pair_then_auth(self):
        c = _BridgeClient(self.port)
        st, info = c.j("I", {})
        self.assertEqual(st, 0)
        a, a_pub = A.keypair()
        st, r = c.j("P", {"name": "Central (Werkstatt)", "A": format(a_pub, "x")})
        self.assertEqual(st, 0, r)
        code = server.PAIR.pending()["code"]
        self.assertEqual(server.PAIR.pending()["kind"], "central")
        b_pub = int(r["B"], 16)
        key = A.derive(code, a_pub, b_pub, A.shared_secret(a, b_pub))
        st, ok = c.j("C", {"request_id": r["request_id"], "mac": A.mac(key, "client", r["request_id"])})
        self.assertEqual(st, 0, ok)
        self.assertEqual(ok["mac"], A.mac(key, "server", ok["client_id"]))
        c.close()
        # neue Verbindung wie bei open(): Anmelden, dann H
        c = _BridgeClient(self.port)
        st, n = c.j("N", {})
        st, _ = c.j("A", {"client_id": ok["client_id"], "mac": A.mac(key, "bridge", n["nonce"])})
        self.assertEqual(st, 0)
        st, _ = c.call("H")
        self.assertEqual(st, bridge.ERR_NO_DEVICE)          # angemeldet; Kit fehlt im Test
        c.close()
        # falsche Unterschrift
        c = _BridgeClient(self.port)
        st, n = c.j("N", {})
        st, err = c.j("A", {"client_id": ok["client_id"], "mac": "00" * 32})
        self.assertEqual(st, bridge.ERR_ACCESS)
        self.assertIn("gekoppelt", err["error"])
        st, _ = c.call("H")
        self.assertEqual(st, bridge.ERR_ACCESS)
        c.close()


if __name__ == "__main__":
    unittest.main()
