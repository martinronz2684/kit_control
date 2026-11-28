"""Laserkorrektur am Pi (kitctl/compensate.py)."""
import math
import struct
import time
import unittest

from kitctl import compensate as C
from kitctl import pjob


def _vectors(data):
    out = []
    z = 0
    for _pos, code, body in pjob._records(data):
        if code == pjob.MAKELAYER:
            z = struct.unpack("<i", body[:4])[0]
        elif code in (pjob.GO, pjob.JUMP):
            x, y = struct.unpack("<ii", body)
            out.append((code, x, y, z))
    return out


def _grid(val_x=0.0, val_y=0.0, step=5.0, half=55.0):
    n = int(round(2 * half / step)) + 1
    return {"step": step, "half": half, "dx": [[val_x] * n for _ in range(n)], "dy": [[val_y] * n for _ in range(n)]}


class CompensateTest(unittest.TestCase):
    def setUp(self):
        self.job = pjob.build([[("contour", [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
                                ("infill", [(1, 5), (9, 5)])]] * 3, 0.1)

    def test_zero_leaves_file_untouched(self):
        out, st = C.apply(self.job, dict(C.ZERO))
        self.assertIs(out, self.job)
        self.assertFalse(st["applied"])
        out, _ = C.apply(self.job, None)
        self.assertIs(out, self.job)
        out, _ = C.apply(self.job, {**C.ZERO, "scale_x_pct": 1.0, "enabled": False})
        self.assertIs(out, self.job)
        out, _ = C.apply(self.job, {**C.ZERO, "grid": _grid()})          # Tabelle voller Nullen
        self.assertIs(out, self.job)

    def test_scale_and_skew_inverse(self):
        comp = C.validate({"scale_x_pct": 1.0, "scale_y_pct": -0.5, "skew_deg": 0.2})
        out, st = C.apply(self.job, comp)
        self.assertTrue(st["applied"])
        sx, sy, e = 1.01, 0.995, math.radians(0.2)
        a = _vectors(self.job)
        b = _vectors(out)
        self.assertEqual(len(a), len(b))
        for (ca, xa, ya, _), (cb, xb, yb, _) in zip(a, b):
            self.assertEqual(ca, cb)
            # Kit brennt L·c – das muss wieder der Sollpunkt sein (±1 µm Rundung)
            bx = sx * xb - sy * math.sin(e) * yb
            by = sy * math.cos(e) * yb
            self.assertAlmostEqual(bx, xa, delta=1.5)
            self.assertAlmostEqual(by, ya, delta=1.5)
        # Header und Schichtbefehle bleiben
        self.assertEqual(out[:512], self.job[:512])
        self.assertEqual(pjob.index(out)["layers"], 3)

    def test_lean_per_layer(self):
        comp = C.validate({"lean_x_mm_per_100": 1.0, "lean_y_mm_per_100": -2.0})
        out, _ = C.apply(self.job, comp)
        for (_, xa, ya, z), (_, xb, yb, _) in zip(_vectors(self.job), _vectors(out)):
            self.assertAlmostEqual(xb, xa - 1.0 * z / 100, delta=1)
            self.assertAlmostEqual(yb, ya + 2.0 * z / 100, delta=1)

    def test_constant_grid_is_pure_shift_without_splitting(self):
        comp = C.validate({"grid": _grid(0.1, -0.05)})
        out, st = C.apply(self.job, comp)
        self.assertEqual(st["vectors_out"], st["vectors_in"])          # Verschiebung hält Linien gerade
        for (_, xa, ya, _), (_, xb, yb, _) in zip(_vectors(self.job), _vectors(out)):
            self.assertEqual((xb - xa, yb - ya), (100, -50))
        self.assertEqual(st["max_shift_mm"], round(math.hypot(0.1, 0.05), 3))

    def test_curved_grid_splits_until_within_tolerance(self):
        g = _grid()
        n = len(g["dx"])
        for j in range(n):
            for i in range(n):
                x, y = i * 5 - 55, j * 5 - 55
                g["dy"][j][i] = 0.0001 * x * x               # Kissen: Mitte einer waagrechten Linie wandert
        comp = C.validate({"grid": g})
        job = pjob.build([[("infill", [(-50, 0), (50, 0)]), ("infill", [(-50, 20), (50, 20)])]], 0.1)
        out, st = C.apply(job, comp)
        self.assertGreater(st["vectors_out"], st["vectors_in"])
        self.assertLess(st["vectors_out"], 100)                       # nur wenige Stücke, nicht 1-mm-Raster
        tf = C.Transform(comp)
        pts = [(code, x / 1000, y / 1000) for code, x, y, _ in _vectors(out)]
        for (c0, x0, y0), (c1, x1, y1) in zip(pts, pts[1:]):
            if c1 != pjob.GO:
                continue
            for t in (0.25, 0.5, 0.75):                               # Sehne gegen echten Bogen
                xm = x0 + (x1 - x0) * t
                # Sollpunkt auf der Linie, der auf xm abgebildet wird: dy hängt nur von x ab, dx = 0
                want_y = tf(xm, y0 - 0.0001 * x0 * x0)[1]
                self.assertLess(abs((y0 + (y1 - y0) * t) - want_y), 0.012)
        JUMP_COUNT = sum(1 for p in pts if p[0] == pjob.JUMP)
        self.assertEqual(JUMP_COUNT, 2)

    def test_grid_bilinear(self):
        g = _grid()
        n = len(g["dx"])
        for j in range(n):
            for i in range(n):
                g["dx"][j][i] = 0.001 * (i * 5 - 55)        # dx = x/1000 (linear -> bilinear exakt)
        tf = C.Transform(C.validate({"grid": g}))
        self.assertAlmostEqual(tf(12.3, -4.0)[0], 12.3 + 0.0123, places=9)
        self.assertAlmostEqual(tf(70.0, 0.0)[0], 70.0 + 0.055, places=9)   # außerhalb: Randwert

    def test_validate_rejects_nonsense(self):
        for bad in ({"scale_x_pct": 6}, {"skew_deg": 4}, {"lean_x_mm_per_100": float("nan")},
                    {"grid": {"step": 5, "half": 55, "dx": [[0]], "dy": [[0]]}},
                    {"grid": _grid(3.0)}):
            with self.assertRaises(ValueError):
                C.validate(bad)

    def test_clamped_to_build_area(self):
        job = pjob.build([[("contour", [(-55, -55), (55, 55)])]], 0.1)
        out, _ = C.apply(job, C.validate({"scale_x_pct": -2.0, "scale_y_pct": -2.0}))
        for _, x, y, _ in _vectors(out):
            self.assertLessEqual(abs(x), C.LIMIT_UM)
            self.assertLessEqual(abs(y), C.LIMIT_UM)

    def test_speed_pure_python(self):
        hatch = []
        for k in range(200):
            y = -50 + k * 0.5
            hatch += [(-50, y), (50, y)] if k % 2 == 0 else [(50, y), (-50, y)]
        job = pjob.build([[("infill", hatch)]] * 50, 0.1)          # 20 000 Vektoren
        t = time.time()
        C.apply(job, C.validate({"scale_x_pct": 0.3, "skew_deg": 0.1}))
        dt = time.time() - t
        self.assertLess(dt, 5.0)


if __name__ == "__main__":
    unittest.main()
