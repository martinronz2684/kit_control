"""Scan-Auswertung des Kalibriermusters (desktop/kitslice/lasercal.py) mit künstlichen Scans bekannter Verzerrung,
und die Kette bis zur Korrektur am Pi (kitctl/compensate.py): korrigiert gebrannt = Soll."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))

from kitctl import compensate as C  # noqa: E402
from kitslice import lasercal as LC  # noqa: E402

SX, SY, EPS, K = 1.004, 0.997, math.radians(0.15), 3e-6
PPM = 600 / 25.4
GRID = np.stack(np.meshgrid(np.linspace(-40, 40, 9), np.linspace(-40, 40, 9)), -1).reshape(-1, 2)


def laser(p):
    """So brennt der (simulierte) Kit einen befohlenen Punkt: Maßstab, Schiefe, Kissenverzerrung ~0,27 mm."""
    x, y = p[:, 0], p[:, 1]
    return np.stack([SX * x - SY * math.sin(EPS) * y + K * x * y * y, SY * math.cos(EPS) * y + K * y * x * x], 1)


def model_err_um(r):
    return float(np.max(np.hypot(*(laser(GRID) - LC.model_of(r)(GRID)).T)) * 1000)


class LaserCalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = LC.synth(PPM, laser, rot_deg=2.3, shift=(1.2, -0.8))
        cls.res = LC.analyze(cls.img, PPM)

    def test_recovers_scale_skew_distortion(self):
        r = self.res
        self.assertAlmostEqual(r["scale_x_pct"], (SX - 1) * 100, delta=0.01)
        self.assertAlmostEqual(r["scale_y_pct"], (SY - 1) * 100, delta=0.01)
        self.assertAlmostEqual(r["skew_deg"], math.degrees(EPS), delta=0.005)
        self.assertAlmostEqual(r["rotation_deg"], 2.3, delta=0.05)        # Papierlage, nur zur Info
        self.assertLess(model_err_um(r), 6)
        self.assertGreater(r["nonlinear_max_um"], 200)
        self.assertLess(r["rms_um"], 5)
        self.assertEqual(r["polarity"], "dark")

    def test_light_lines_and_quarter_turn(self):
        img = LC.synth(PPM, laser, rot_deg=-4.1, shift=(-2, 1.5), dark=False)
        r = LC.analyze(img, PPM)
        self.assertEqual(r["polarity"], "light")
        self.assertLess(model_err_um(r), 8)
        # Papier um 90° gedreht eingescannt, Lage in der App auf 90° gestellt
        r = LC.analyze(np.rot90(self.img, k=1), PPM, rot90=1)
        self.assertLess(model_err_um(r), 8)

    def test_two_scans_cancel_scanner_skew(self):
        sk = 0.0015                                       # Scanner: Schlitten nicht rechtwinklig (0,086°)

        def scan(quarter):
            ph = math.radians(90 * quarter)

            def fwd(p):
                q = laser(p)
                q = np.stack([math.cos(ph) * q[:, 0] - math.sin(ph) * q[:, 1],
                              math.sin(ph) * q[:, 0] + math.cos(ph) * q[:, 1]], 1)
                return np.stack([q[:, 0] + sk * q[:, 1], q[:, 1]], 1)
            return LC.analyze(LC.synth(PPM, fwd, rot_deg=0.6, seed=quarter), PPM, rot90=quarter)
        a, b = scan(0), scan(1)
        self.assertGreater(abs(a["skew_deg"] - math.degrees(EPS)), 0.06)    # einzeln: Scannerfehler drin
        both = LC.combine([a, b])
        self.assertAlmostEqual(both["skew_deg"], math.degrees(EPS), delta=0.006)
        self.assertEqual(both["scans"], 2)

    def test_correction_on_pi_cancels_laser_error(self):
        comp = C.validate(LC.compensation(self.res))
        self.assertTrue(C.active(comp))
        self.assertIsNotNone(comp["grid"])
        tf = C.Transform(comp)
        d = np.stack(np.meshgrid(np.linspace(-38, 38, 9), np.linspace(-38, 38, 9)), -1).reshape(-1, 2)
        c = np.array([tf(x, y) for x, y in d])
        burned = laser(c)
        # Maschinenrahmen der Auswertung: Laser-X-Achse bleibt, also direkt vergleichbar
        err = np.hypot(*(burned - d).T) * 1000
        self.assertLess(err.max(), 12)
        uncorrected = np.hypot(*(laser(d) - d).T) * 1000
        self.assertGreater(uncorrected.max(), 150)
        # ohne Maßstab: bleibt gemessener Maßstab übrig (läuft über die Skalierung im Kit), Rest korrigiert
        comp = C.validate(LC.compensation(self.res, use_scale=False))
        self.assertEqual(comp["scale_x_pct"], 0.0)
        tf = C.Transform(comp)
        c = np.array([tf(x, y) for x, y in d])
        want = d * [self.res["scale_x_pct"] / 100 + 1, self.res["scale_y_pct"] / 100 + 1]
        self.assertLess(np.max(np.hypot(*(laser(c) - want).T)) * 1000, 12)

    def test_deviation_lines_for_display(self):
        lines = LC.deviation_lines(self.res)
        self.assertEqual(len(lines), len(LC.segments()))
        corner = [pt for pt in lines[0] if abs(pt[0] + 40) < 1e-6][0]
        self.assertGreater(math.hypot(corner[2], corner[3]), 0.05)

    def test_errors(self):
        with self.assertRaises(LC.CalError):
            LC.analyze(np.full((2400, 2400), 230, np.uint8), PPM)
        with self.assertRaises(LC.CalError):
            LC.analyze(self.img[:1500, :1500], PPM)                          # Muster abgeschnitten
        with self.assertRaises(LC.CalError):
            LC.analyze(self.img, 1.0)


if __name__ == "__main__":
    unittest.main()
