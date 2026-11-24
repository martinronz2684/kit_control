import struct
import unittest

from kitctl import protocol as P
from kitctl.client import Kit


class FakeKit:
    """Answers like a Kit M2 with firmware 12, as far as Central's parsers tell us."""

    def __init__(self, model=4, firm=12, comm=4):
        self.sent = []
        self.model, self.firm, self.comm = model, firm, comm
        self._next = b""

    def write(self, data):
        self.sent.append(bytes(data))
        c = P.code_of(data)
        le = lambda v: struct.pack("<i", v)
        if c == P.COM_IDENTIFY:
            self._next = P.code(P.SIG_IDENTIFY) + struct.pack("<III", self.model, self.comm, self.firm) + bytes(range(16))
        elif c == P.COM_CONNECTION_ESTABLISHED:
            self._next = P.code(P.SIG_OPERATION_SUCCESSFUL) + b"\x01"
        elif c == P.COM_REQUESTGENERALPRINTERSTATE:
            self._next = P.code(P.SIG_GENERALPRINTERSTATE) + b"\x03" + le(1) + le(0)
        elif c == P.COM_REQUESTPRINTSTATUS:
            self._next = P.code(P.SIG_PRINTSTATUS) + b"\x01" + le(412) + le(15120) + le(61)
        elif c == P.COM_REQUESTPOWDERSURFACETEMP:
            self._next = P.code(P.SIG_SINGLETEMPERATURE) + le(168400)
        elif c == P.COM_REQUESTCHAMBERTEMP:
            self._next = P.code(P.SIG_SINGLETEMPERATURE) + le(141200)
        elif c == P.COM_REQUEST_LIVEPARAMETERS1:
            self._next = P.code(P.SIG_LIVEPARAMETERS1) + b"".join(le(v) for v in (130000, 150000, 145000, 170000, 1500000))
        elif c == P.COM_REQUEST_PRINTWARMUPCOUNTDOWN:
            self._next = P.code(P.SIG_WARMUPPRINTCOUNTDOWN) + b"\x00" + le(0)
        else:
            self._next = P.code(P.SIG_UNKNOWN_COMMAND)

    def read(self, size):
        return self._next

    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_codes_little_endian(self):
        self.assertEqual(P.code(P.COM_IDENTIFY), bytes([0x8B, 0x13]))   # Central: [-117, 19]
        self.assertEqual(P.code(P.COM_STARTPRINT), bytes([14, 0]))

    def test_connect_and_snapshot(self):
        fake = FakeKit()
        kit = Kit(fake)
        ident = kit.connect()
        self.assertEqual(ident.model_name, "KitM2USBV")
        snap = kit.snapshot()
        self.assertTrue(snap["print"].printing)
        self.assertEqual(snap["print"].layer, 412)
        self.assertAlmostEqual(snap["surface"].celsius, 168.4)
        self.assertAlmostEqual(snap["live"].chamber_print, 145.0)
        self.assertEqual(snap["state"].warnings, 1)

    def test_bootloader_is_never_flashed(self):
        kit = Kit(FakeKit(model=0))
        with self.assertRaises(P.ProtocolError):
            kit.connect()
        with self.assertRaises(P.ProtocolError):
            kit.transact(P.code(P.COM_FIRMWARE_FLASHING_REQUEST), 3)

    def test_old_firmware_is_rejected_not_flashed(self):
        fake = FakeKit(firm=11)
        with self.assertRaises(P.ProtocolError):
            Kit(fake).connect()
        self.assertEqual([P.code_of(s) for s in fake.sent], [P.COM_IDENTIFY])

    def test_error_frame(self):
        buf = P.code(P.SIG_ERRORFRAME) + bytes([2]) + struct.pack("<ii", 4, 96) + bytes(500)
        self.assertEqual(P.Frame.parse(buf, P.SIG_ERRORFRAME).codes, [4, 96])
        self.assertEqual(P.Frame.parse(P.code(P.SIG_WARNINGFRAME) + b"\x00", P.SIG_WARNINGFRAME).codes, [])
        from kitctl.codes import describe
        self.assertEqual(describe(96)["title"], "Beschichter klemmt")
        self.assertEqual(describe(7)["kind"], "Unbekannt")

    def test_commands_bytes(self):
        self.assertEqual(P.cmd_move("print", 1.0), bytes([25, 0, 0]) + struct.pack("<i", 1000))
        self.assertEqual(P.cmd_lamp("left", 80), bytes([34, 0]) + struct.pack("<i", 800))
        self.assertEqual(P.cmd_target("chamber_warmup", 145), bytes([47, 0]) + struct.pack("<i", 145000))
        self.assertEqual(P.cmd_warmup(True), bytes([35, 0, 1]))

    def test_layer_thickness_in_um(self):
        self.assertEqual(P.mm_to_um(0.1), struct.pack("<i", 100))


if __name__ == "__main__":
    unittest.main()


def test_kalibrierung_wie_central():
    # Testmuster: Code + 1 Byte (1 Muster, 2 Mittelpunkt, 0 aus, 4 Referenzfahrt)
    assert P.cmd_test_pattern("pattern") == P.code(P.COM_TESTPATTERN) + b"\x01"
    assert P.cmd_test_pattern("home")[-1] == 4
    # Scaling: Faktor x 10000 als int32 LE; Prozent wie Central gerundet; max ±5 %
    assert P.scaling_factor(1.25) == 1.0125
    assert P.cmd_scaling(1.0125, 1.0, 0.99)[2:] == struct.pack("<iii", 10125, 10000, 9900)
    import pytest
    with pytest.raises(ValueError):
        P.scaling_factor(5.2)
    # Berechnen: (Faktor * Soll / Ist - 1) * 100
    assert abs(P.new_scaling_percent(1.0, 50, 49.5) - 1.0101) < 1e-3
    sc = P.ScalingParameters.parse(P.code(P.SIG_SCALINGPARAMETERS1) + struct.pack("<iii", 10125, 10000, 9950))
    assert (sc.x, sc.y, sc.z) == (1.0125, 1.0, 0.995)


class HandshakeTests(unittest.TestCase):
    def test_ohne_verbindungsbestaetigung_wenn_kit_antwortet(self):
        # Kein COM_CONNECTION_ESTABLISHED, wenn der Kit schon auf Statusabfragen antwortet (sonst Referenzfahrt)
        import os
        os.environ["KIT_HANDSHAKE"] = "auto"
        fake = FakeKit()
        kit = Kit(fake)
        kit.connect()
        del os.environ["KIT_HANDSHAKE"]
        self.assertFalse(kit.handshake)
        self.assertNotIn(P.code(P.COM_CONNECTION_ESTABLISHED), [d[:2] for d in fake.sent])

    def test_bestaetigung_nur_als_rueckfall(self):
        class Stumm(FakeKit):
            ok = False
            def write(self, data):
                super().write(data)
                c = P.code_of(data)
                if c == P.COM_CONNECTION_ESTABLISHED:
                    Stumm.ok = True
                if c == P.COM_REQUESTGENERALPRINTERSTATE and not Stumm.ok:
                    self._next = P.code(P.SIG_UNKNOWN_COMMAND)
        import os
        os.environ["KIT_HANDSHAKE"] = "auto"
        kit = Kit(Stumm())
        kit.connect()
        del os.environ["KIT_HANDSHAKE"]
        self.assertTrue(kit.handshake)

    def test_standard_wie_central(self):
        fake = FakeKit()
        Kit(fake).connect()
        self.assertIn(P.code(P.COM_CONNECTION_ESTABLISHED), [d[:2] for d in fake.sent])


class ReferenzfahrtTests(unittest.TestCase):
    def test_pi_stoesst_referenzfahrt_nie_selbst_an(self):
        # Nur mit ausdrücklicher Bestätigung vom Bildschirm; sonst abgelehnt
        import kitd.server as S
        w = S.KitWorker.__new__(S.KitWorker)
        w.snapshot = lambda: {"printing": False}
        with self.assertRaises(ValueError):
            w._encode({"cmd": "pattern", "name": "home"})
        self.assertEqual(w._encode({"cmd": "pattern", "name": "home", "confirmed": True})[-1], 4)
        # Verbindungsaufbau schickt keine Referenzfahrt
        fake = FakeKit()
        Kit(fake).connect()
        self.assertNotIn(P.code(P.COM_TESTPATTERN), [d[:2] for d in fake.sent])
