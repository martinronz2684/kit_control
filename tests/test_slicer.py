import json
import math
import os
import tempfile
import threading
import unittest
import urllib.request

import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))

os.environ.setdefault("KIT_STATE_DIR", tempfile.mkdtemp(prefix="kitd-test-"))
os.environ["KIT_PROFILE_DIR"] = tempfile.mkdtemp(prefix="kit-prof-")

from kitctl import pjob  # noqa: E402
from kitslice import polygon as G, profiles, stl  # noqa: E402
from kitslice.job import make_job  # noqa: E402
from kitslice.scene import Part, Scene  # noqa: E402
from kitslice.slicer import SliceSettings, slice_mesh  # noqa: E402


def box(w, d, h, x=0.0, y=0.0, z=0.0):
    v = np.array([[x + a, y + b, z + c] for a in (0, w) for b in (0, d) for c in (0, h)], float)
    f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
         (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    return v[np.array(f)]


class PolygonTest(unittest.TestCase):
    def test_orient_and_offset(self):
        outer = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)[::-1]   # im Uhrzeigersinn geliefert
        hole = np.array([[4, 4], [6, 4], [6, 6], [4, 6]], float)
        o, h = G.orient([outer, hole])
        self.assertGreater(G.area(o), 0)
        self.assertLess(G.area(h), 0)
        oo, hh = G.offset([o, h], 0.5)
        self.assertAlmostEqual(G.area(oo), 81.0, places=6)     # 9 x 9
        self.assertAlmostEqual(-G.area(hh), 9.0, places=6)     # Loch wächst auf 3 x 3

    def test_offset_collapses_thin_part(self):
        thin = G.orient([np.array([[0, 0], [10, 0], [10, 0.3], [0, 0.3]], float)])[0]
        self.assertIsNone(G.offset_loop(thin, 0.2))

    def test_hatch_grid_and_order(self):
        sq = G.orient([np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)])
        segs = G.hatch(sq, 1.0, 0.0)
        ys = [s[1] for s in segs]
        self.assertEqual(ys, sorted(ys, reverse=True))          # von oben nach unten
        self.assertEqual(ys[0], 9.0)                            # festes Raster y = k * Abstand
        self.assertGreater(segs[0][0], segs[0][2])               # erste Linie von rechts nach links
        self.assertLess(segs[1][0], segs[1][2])                  # dann Zickzack
        self.assertEqual(len(segs), 10)                          # y = 0 .. 9 (halboffen)


class SlicerTest(unittest.TestCase):
    def test_box_pa12(self):
        s = SliceSettings.from_profile(profiles.get("pa12"))
        layers = slice_mesh(box(20, 10, 1, -10, -5), s)
        self.assertEqual(len(layers), 10)
        c = layers[0].contours
        self.assertEqual(len(c), 1)
        self.assertAlmostEqual(c[0][:, 0].max(), 9.8, places=6)  # 0,2 mm Kontur nach innen
        h = np.array(layers[0].hatches)
        self.assertLessEqual(np.abs(h[:, [0, 2]]).max(), 9.75 + 1e-6)   # 0,25 mm Füllversatz
        # Winkel reihum 45°, -45°, -135°, 135°
        d0 = h[0, 2:] - h[0, :2]
        d1 = np.array(layers[1].hatches[0][2:]) - np.array(layers[1].hatches[0][:2])
        self.assertAlmostEqual(math.degrees(math.atan2(d0[1], d0[0])) % 180, 45, places=3)
        self.assertAlmostEqual(math.degrees(math.atan2(d1[1], d1[0])) % 180, 135, places=3)

    def test_job_roundtrip_and_empty_layers(self):
        # zwei Teile übereinander mit 3 mm Lücke -> 30 leere Schichten, Central schreibt nur 20
        tris = np.concatenate([box(5, 5, 1), box(5, 5, 1, 0, 0, 4)])
        p = Part("t", tris)
        sc = Scene([p])
        data, meta, layers = make_job(sc, profiles.get("pa12"))
        self.assertEqual(len(layers), 50)
        self.assertEqual(meta["layers"], 10 + 20 + 10)
        idx = pjob.index(data)
        self.assertEqual(idx["z_um"][:3], [100, 200, 300])
        self.assertEqual(idx["z_um"][-1], 4000)

    def test_scene_arrange_and_problems(self):
        sc = Scene([Part("a", box(40, 40, 5)), Part("b", box(40, 40, 5)), Part("c", box(40, 40, 5))])
        self.assertTrue(sc.arrange())
        self.assertEqual(sc.problems(), [])
        sc.parts[1].x = sc.parts[0].x
        sc.parts[1].y = sc.parts[0].y
        self.assertTrue(any("überlappen" in m for m in sc.problems()))
        big = Scene([Part("x", box(120, 10, 5))])
        self.assertTrue(any("außerhalb" in m for m in big.problems()))

    def test_stl_roundtrip(self):
        f = os.path.join(tempfile.mkdtemp(), "b.stl")
        stl.save_binary(box(3, 4, 5), f)
        self.assertEqual(stl.load(f).shape, (12, 3, 3))


class NestTest(unittest.TestCase):
    def test_nest_stacks_and_stays_in_ideal_area(self):
        sc = Scene([Part(f"b{i}", box(40, 30, 15)) for i in range(6)])
        self.assertTrue(sc.nest())
        self.assertEqual(sc.problems(), [])
        self.assertEqual(sc.notes(), [])
        self.assertGreater(max(p.z_lift for p in sc.parts), 0)          # übereinander gestapelt
        for p in sc.parts:
            lo, hi = p.bbox()
            self.assertGreaterEqual(lo[0], -45.01); self.assertLessEqual(hi[0], 45.01)

    def test_nest_only_new_keeps_old(self):
        a = Part("a", box(30, 30, 10))
        sc = Scene([a])
        a.x, a.y = 10.0, 10.0
        b = Part("b", box(30, 30, 10))
        sc.add(b)
        sc.nest(only=[b])
        self.assertEqual((a.x, a.y), (10.0, 10.0))
        self.assertEqual(sc.problems(), [])

    def test_collision_columns(self):
        sc = Scene([Part("a", box(20, 20, 10)), Part("b", box(20, 20, 10))])
        self.assertTrue(sc.collisions())
        sc.parts[1].z_lift = 11
        self.assertFalse(sc.collisions())


class StrategyTest(unittest.TestCase):
    def test_strategies_run_and_change_output(self):
        base = profiles.validate(profiles.get("pa12"))
        sc = Scene([Part("b", box(20, 20, 2))])
        d0, m0, _ = make_job(sc, base)
        d1, m1, L = make_job(sc, profiles.validate(dict(base, skin_layers=3, core_spacing_um=360, island_mm=5,
                                                         hatch_angle_step_deg=67, optimize_path=True,
                                                         contour_first=False, shrink_pct={"x": 1, "y": 1, "z": 0})))
        self.assertNotEqual(d0, d1)
        self.assertAlmostEqual(m1["bbox"][2] - m1["bbox"][0], (20 * 1.01) - 0.4, places=1)
        with self.assertRaises(ValueError):
            profiles.validate(dict(base, core_spacing_um=50))


class ThinWallTest(unittest.TestCase):
    def test_thin_wall_kept(self):
        sc = Scene([Part("wand", box(30, 0.3, 2))])
        _, m, _ = make_job(sc, profiles.validate(profiles.get("pa12")))
        self.assertGreater(m["vectors"], 0)


class ProfileTest(unittest.TestCase):
    def test_save_derive_validate(self):
        p = profiles.derive("pa12", "Mein PA12 schwarz")
        p["hatch_spacing_um"] = 100
        p["lamps"] = {"left": 80, "right": 100, "front": 100}
        saved = profiles.save(p)
        self.assertEqual(profiles.get(saved["id"])["hatch_spacing_um"], 100)
        with self.assertRaises(ValueError):
            profiles.save(dict(saved, hatch_spacing_um=5))
        with self.assertRaises(ValueError):
            profiles.save(profiles.get("pa12"))
        profiles.delete(saved["id"])


class UploadTest(unittest.TestCase):
    def test_upload_without_kit(self):
        from http.server import ThreadingHTTPServer
        from kitd import server
        from kitslice.net import Pi
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            data = pjob.build_central([([[(0, 0), (5, 0), (5, 5)]], [(1, 1, 4, 1)])], 0.1)
            r = Pi("127.0.0.1", srv.server_address[1]).send_job(data, "Test ä", profiles.get("pa12"), start=True)
            self.assertTrue(r["ok"])
            self.assertFalse(r["started"])                        # kein Kit verbunden
            self.assertIn("Kein Kit", r["start_error"])
            self.assertEqual(r["job"]["name"], "Test ä")
            self.assertEqual(r["job"]["profile"]["temps"]["surface_print"], 170)
            st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/state").read())
            self.assertIn("connected", st)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
