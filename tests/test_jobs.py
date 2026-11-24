import os
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest

os.environ["KIT_STATE_DIR"] = tempfile.mkdtemp(prefix="kitd-test-")

from kitctl import ftp, pjob, protocol as P  # noqa: E402
from kitctl.client import Kit  # noqa: E402
from kitd import bridge, jobs  # noqa: E402
from kitd.demo import DemoTransport  # noqa: E402


class PjobTest(unittest.TestCase):
    def test_roundtrip(self):
        sq = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        data = pjob.build([[("contour", sq), ("infill", [(1, 5), (9, 5)])], [], [("contour", sq)]], 0.1)
        idx = pjob.index(data)
        self.assertEqual(idx["layers"], 2)               # leere Schicht schreibt Central nicht
        self.assertEqual(idx["z_um"], [100, 300])
        self.assertEqual(idx["layer_mm"], 0.1)
        self.assertEqual(idx["bbox"], [0, 0, 10, 10])
        L = pjob.layer(data, idx, 1)
        self.assertEqual(len(L["contour"]), 4 * 4)
        self.assertEqual(L["infill"], [1, 5, 9, 5])
        self.assertEqual(pjob.layer(data, idx, 2)["infill"], [])

    def test_record_layout_like_central(self):
        data = pjob.build([[("contour", [(1.5, 2), (3, 4)])]], 0.1)
        self.assertEqual(data[:512], bytes(512))
        self.assertEqual(data[512:522], struct.pack("<Hii", 27, 100, 0))      # MakeLayer z µm, Nr
        self.assertEqual(data[522:524], struct.pack("<H", 73))                 # Kontur
        self.assertEqual(data[524:534], struct.pack("<Hii", 2, 1500, 2000))    # Jump
        self.assertEqual(data[534:544], struct.pack("<Hii", 1, 3000, 4000))    # Go


class FtpTest(unittest.TestCase):
    def test_send_to_demo_kit(self):
        t = DemoTransport()
        data = pjob.demo_job()[:20000] + b"x" * 7
        ftp.send_file(t, data)
        self.assertEqual(t.file, data)

    def test_not_ready(self):
        class Busy:
            def write(self, d): pass
            def read(self, n): return P.code(3001) + b"\x00\x01"
        with self.assertRaises(ftp.NotReady):
            ftp.send_file(Busy(), b"abc")


class FakeWorker:
    def __init__(self):
        self.kit = Kit(DemoTransport())
        self.kit.connect()
        self.usb = threading.RLock()
        self.state = {}

    def _set(self, **kw):
        self.state.update(kw)

    def snapshot(self):
        return dict(self.state)

    def set_current_job(self, meta):
        self.state["current_job"] = meta


class BridgeCaptureTest(unittest.TestCase):
    """Central überträgt über die WLAN-Brücke: Pi speichert eine Kopie; Autostart entscheidet über den Druckstart."""

    def setUp(self):
        self.w = FakeWorker()
        bridge.Session.worker = self.w
        self.srv = bridge._Server(("127.0.0.1", 0), bridge.Session)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.s = socket.create_connection(self.srv.server_address)

    def tearDown(self):
        self.s.close()
        self.srv.shutdown()
        self.srv.server_close()

    def _xfer(self, op, data=b"", n=0):
        self.s.sendall(struct.pack(">cBII", op, 6, 2000, len(data) if op == b"W" else n) + data)
        st, ln = struct.unpack(">iI", bridge._recv(self.s, 8))
        return st, bridge._recv(self.s, ln)

    def _central_prints(self, data):
        class Via:
            def write(s2, d): self._xfer(b"W", bytes(d))
            def read(s2, n): return self._xfer(b"R", n=n)[1]
        ftp.send_file(Via(), data)
        self._xfer(b"W", P.code(P.COM_STARTPRINT))
        return self._xfer(b"R", n=512)[1]

    def _wait_indexed(self):
        for _ in range(100):
            j = jobs.listing()[0]
            if "layers" in j or j.get("error"):
                return j
            time.sleep(0.05)
        self.fail("nicht ausgewertet")

    def test_autostart_on(self):
        jobs.set_autostart(True)
        data = pjob.build([[("contour", [(0, 0), (5, 5)])]] * 3)
        ans = self._central_prints(data)
        self.assertEqual(ans[2], 1)
        self.assertTrue(self.w.kit.t.printing)
        j = self._wait_indexed()
        self.assertEqual(jobs.data(j["id"]), data)
        self.assertEqual(j["layers"], 3)
        self.assertEqual(self.w.state["current_job"]["id"], j["id"])

    def test_autostart_off(self):
        jobs.set_autostart(False)
        data = pjob.build([[("contour", [(0, 0), (5, 5)])]] * 2)
        ans = self._central_prints(data)
        self.assertEqual(ans[2], 0)                       # Central erfährt: nicht gestartet
        self.assertFalse(self.w.kit.t.printing)
        self.assertEqual(jobs.data(jobs.listing()[0]["id"]), data)
        self.assertIs(self.w.state["central_job"]["started"], False)


class StartFromPiTest(unittest.TestCase):
    def test_start_job(self):
        import kitd.server as S
        w = S.KitWorker()
        w.kit = Kit(DemoTransport())
        w.kit.connect()
        w.demo = True   # Quelle "demo" darf nur im Demo-Modus starten
        meta = jobs.save(pjob.build([[("contour", [(0, 0), (5, 5)])]] * 5), "demo", "Test")
        q = queue.Queue()
        w._start_job(meta["id"], q)
        self.assertTrue(q.get_nowait()["ok"])
        self.assertTrue(w.snapshot()["job_result"]["ok"], w.snapshot())
        self.assertTrue(w.kit.t.printing)
        self.assertEqual(w.kit.t.layers, 5)
        self.assertEqual(jobs.get(meta["id"])["starts"], 1)

    def test_start_job_with_profile(self):
        import kitd.server as S
        w = S.KitWorker()
        w.kit = Kit(DemoTransport())
        w.kit.connect()
        meta = jobs.save(pjob.build([[("contour", [(0, 0), (5, 5)])]] * 3), "pc", "Mit Profil")
        prof = {"name": "PA12", "temps": {"surface_warmup": 150, "chamber_warmup": 140, "surface_print": 170,
                                          "chamber_print": 140}, "lamps": {"left": 80, "right": 100, "front": 100}}
        jobs.update(meta["id"], profile=prof)
        q = queue.Queue()
        w._start_job(meta["id"], q)
        self.assertTrue(q.get_nowait()["ok"])
        self.assertTrue(w.snapshot()["job_result"]["ok"], w.snapshot())
        self.assertEqual(w.snapshot()["lamps"]["left"], 80)


if __name__ == "__main__":
    unittest.main()
