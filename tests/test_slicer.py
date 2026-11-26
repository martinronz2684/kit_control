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
        # zwei Quader in einem Netz mit 3 mm Lücke. Wie Central: der untere bekommt an seiner
        # Oberseite (genau auf der Schichtgrenze z = 1,0) eine eigene Schicht, dann 29 leere
        # Schichten (Central schreibt nur 20), oben 10 Schichten (nichts über der Oberkante)
        tris = np.concatenate([box(5, 5, 1), box(5, 5, 1, 0, 0, 4)])
        p = Part("t", tris)
        sc = Scene([p])
        data, meta, layers = make_job(sc, profiles.get("pa12"))
        self.assertEqual(len(layers), 50)
        self.assertEqual(meta["layers"], 11 + 20 + 10)
        idx = pjob.index(data)
        self.assertEqual(idx["z_um"][:3], [100, 200, 300])
        self.assertEqual(idx["z_um"][-1], 4100)

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
        self.assertLessEqual(max(p.bbox()[1][2] for p in sc.parts), 33.01)   # niedriger als gestapelt
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


class OrientTest(unittest.TestCase):
    def test_flat_plate_stands_up_in_quality_mode(self):
        from kitslice import packing
        sc = Scene([Part("platte", box(70, 50, 3))])
        packing.auto_pack(sc, time_budget=0.5, quality_w=1.0)
        self.assertGreater(sc.parts[0].size()[2], 20)          # nicht flach liegend (Verzug)

    def test_no_empty_layers(self):
        from kitslice import packing
        sc = Scene([Part(f"b{i}", box(30 + i * 3, 25, 10 + i * 4)) for i in range(7)])
        r = packing.auto_pack(sc, time_budget=1.0)
        self.assertEqual(r["empty_mm"], 0.0)
        self.assertEqual(sc.problems(), [])


class PackTest(unittest.TestCase):
    def test_auto_pack_and_fill(self):
        from kitslice import packing
        sc = Scene([Part(f"b{i}", box(40, 30, 15)) for i in range(4)] + [Part("stab", box(70, 8, 8))])
        r = packing.auto_pack(sc, time_budget=1)
        self.assertTrue(r["ok"])
        self.assertEqual(sc.problems(), [])
        self.assertLessEqual(r["height"], 40)
        n = packing.fill(sc, sc.parts[-1], limit=5)
        self.assertEqual(n, 5)
        self.assertEqual(sc.problems(), [])

    def test_locked_part_stays(self):
        from kitslice import packing
        a = Part("a", box(20, 20, 10), x=5.0, y=5.0, lock_pos=True)
        sc = Scene([a, Part("b", box(20, 20, 10))])
        packing.auto_pack(sc, time_budget=0.5)
        self.assertEqual((a.x, a.y, a.z_lift), (5.0, 5.0, 0.0))
        self.assertEqual(sc.problems(), [])


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


class OffsetRobustTest(unittest.TestCase):
    def test_offset_never_leaves_shape(self):
        rng = np.random.default_rng(3)
        for _ in range(2000):
            n = int(rng.integers(5, 40))
            t = np.sort(rng.random(n)) * 2 * np.pi
            r = 2 + rng.random(n) * 3
            poly = G.orient([np.stack([np.cos(t) * r, np.sin(t) * r], 1)])[0]
            q = G.offset_loop(poly, 0.2)
            if q is not None:
                self.assertTrue(np.isfinite(q).all())
                self.assertLessEqual(np.abs(q).max(), np.abs(poly).max() + 0.8 + 1e-6)


class BigMeshTest(unittest.TestCase):
    def test_many_vertices_closed_contours(self):
        # > 46341 Eckpunkte: Kantenschlüssel passen nicht mehr in int32 (früher zerfielen die Konturen)
        u, v = np.meshgrid(np.linspace(0, np.pi, 180), np.linspace(0, 2 * np.pi, 360))
        P = np.stack([np.sin(u) * np.cos(v) * 15, np.sin(u) * np.sin(v) * 15, np.cos(u) * 15 + 15], -1)
        a, b, c, d = P[:-1, :-1], P[1:, :-1], P[1:, 1:], P[:-1, 1:]
        T = np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)])
        sc = Scene([Part("kugel", T), Part("kugel2", T, x=40.0)])
        _, m, L = make_job(sc, profiles.validate(profiles.get("pa12")))
        mid = L[len(L) // 2]
        self.assertEqual(len(mid.contours), 2)
        self.assertGreater(len(mid.hatches), 100)


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

def obox(w, d, h, x=0.0, y=0.0, z=0.0):
    """Quader mit nach außen zeigenden Flächen (wie eine echte STL)."""
    return box(w, d, h, x, y, z)[:, ::-1]


class CentralRulesTest(unittest.TestCase):
    """Regeln, die am echten Central 1.2.0 gemessen wurden (Schnitte an den Schichtgrenzen)."""

    def sec(self, tris):
        from kitslice.central import part_sections
        return part_sections(tris, 0.1)

    @staticmethod
    def area(loops):
        return abs(sum(G.area(l) for l in G.orient([np.asarray(l) for l in loops])))

    def test_box_layers_from_bottom(self):
        r = self.sec(obox(20, 20, 1))
        self.assertEqual(sorted(r), list(range(10)))             # 0,0 … 0,9; Oberseite bekommt keine Schicht
        self.assertAlmostEqual(self.area(r[0]), 400.0, places=3)  # Boden bei z = 0 gehört zur Schicht 0

    def test_unaligned_top_keeps_material(self):
        # Central verliert hier durch einen Fehler die oberste Schicht (5,0 … 5,03 mm) – wir nicht
        self.assertEqual(len(self.sec(obox(20, 20, 5.03))), 51)

    @staticmethod
    def extrude(profile, depth):
        """Profil in der XZ-Ebene entlang y extrudieren -> geschlossene Hülle mit Normalen nach außen."""
        P = np.asarray(profile, float)
        T = []
        for i in range(1, len(P) - 1):
            a, b, c = P[0], P[i], P[i + 1]
            T.append([[a[0], 0, a[1]], [b[0], 0, b[1]], [c[0], 0, c[1]]])
            T.append([[a[0], depth, a[1]], [c[0], depth, c[1]], [b[0], depth, b[1]]])
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            q = np.array([[a[0], 0, a[1]], [b[0], 0, b[1]], [b[0], depth, b[1]], [a[0], depth, a[1]]])
            T += [q[[0, 2, 1]], q[[0, 3, 2]]]
        T = np.array(T, float)
        if np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() < 0:
            T = T[:, ::-1]
        return T

    def test_flat_faces_on_plane_are_drawn(self):
        # Flache Flächen genau auf der Ebene zeichnet Central mit – nach oben wie nach unten zeigend
        step = self.extrude([(0, 0), (30, 0), (30, 2), (10, 2), (10, 3), (0, 3)], 30)
        over = self.extrude([(10, 0), (20, 0), (20, 2), (30, 2), (30, 3), (0, 3), (0, 2), (10, 2)], 30)
        self.assertAlmostEqual(self.area(self.sec(step)[20]), 900.0, places=2)
        self.assertAlmostEqual(self.area(self.sec(step)[21]), 300.0, places=2)
        self.assertAlmostEqual(self.area(self.sec(over)[19]), 300.0, places=2)
        self.assertAlmostEqual(self.area(self.sec(over)[20]), 900.0, places=2)

    def test_slanted_cut_at_boundary(self):
        a = np.array([[0, 0, 0], [20, 0, 0], [20, 20, 0], [0, 20, 0]], float)
        t = np.array([10, 10, 5.0])
        tris = [a[[0, 2, 1]], a[[0, 3, 2]]] + [np.array([a[i], a[(i + 1) % 4], t]) for i in range(4)]
        r = self.sec(np.array(tris))
        pts = np.vstack(r[10])                                   # Schicht 10 = Schnitt genau bei z = 1,0
        self.assertAlmostEqual(pts[:, 0].max() - pts[:, 0].min(), 16.0, places=4)

    def test_layer_height_is_boundary(self):
        s = SliceSettings.from_profile(profiles.get("pa12"))
        layers = slice_mesh(obox(20, 10, 1, -10, -5), s)
        self.assertEqual([round(L.z, 3) for L in layers[:3]], [0.0, 0.1, 0.2])

class LayerTimeFitTest(unittest.TestCase):
    def test_fit_recoat_and_laser_factor(self):
        from kitslice.job import fit_layer_times, estimate_seconds
        rng = np.random.default_rng(1)
        rows = []
        for i in range(200):
            scan, jump, v = rng.uniform(500, 6000), rng.uniform(100, 800), 650.0
            rows.append([i, 48 + 1.3 * scan / v + jump / 2000 + rng.normal(0, 1.5), scan, jump, v])
        rows[50][1] = 900                                   # Pause am Kit – darf nicht mitzählen
        m = fit_layer_times([{"rows": rows}])
        self.assertAlmostEqual(m["recoat_s"], 48, delta=1.5)
        self.assertAlmostEqual(m["scan_k"], 1.3, delta=0.05)
        t = estimate_seconds({"est_scan_m": 0, "est_jump_m": 0, "layers": 100}, 650, m["recoat_s"], scan_k=m["scan_k"])
        self.assertAlmostEqual(t, 100 * m["recoat_s"], places=3)
        self.assertIsNone(fit_layer_times([{"rows": rows[:10]}]))   # zu wenig Schichten

def cup(w=34, h=30, t=2):
    """Oben offener Becher aus dicht aneinanderliegenden Quadern."""
    return np.concatenate([obox(w, w, t), obox(t, w, h - t, 0, 0, t), obox(t, w, h - t, w - t, 0, t),
                           obox(w - 2 * t, t, h - t, t, 0, t), obox(w - 2 * t, t, h - t, t, w - t, t)])


class NestingTest(unittest.TestCase):
    def test_true_shape_keeps_cavity_free(self):
        from kitslice.scene import dexels, dexels_overlap
        c = dexels(cup(), 0.5)
        inside = dexels(obox(10, 10, 10, 12, 12, 6), 0.5)
        self.assertFalse(dexels_overlap(c, inside))            # Klotz im Becher berührt nichts
        self.assertTrue(dexels_overlap(c, dexels(obox(10, 10, 10, 12, 12, 0), 0.5)))   # im Boden: ja

    def test_small_parts_go_into_cups_without_interlocking(self):
        from kitslice import packing
        parts = [Part(f"becher{i}", cup(), lock_orient=True) for i in range(4)] + \
                [Part(f"klotz{i}", obox(14, 14, 14)) for i in range(4)]
        sc = Scene(parts)
        r = packing.auto_pack(sc, time_budget=2.0)
        self.assertEqual(sc.problems(), [])
        self.assertLessEqual(r["height"], 30.5)                # alles in einer Lage: Klötze in den Bechern
        self.assertEqual(r["empty_mm"], 0.0)

    def test_arranging_again_never_gets_worse(self):
        from kitslice import packing
        sc = Scene([Part(f"b{i}", obox(20 + i * 4, 18, 10 + i * 3), lock_orient=(i % 2 == 0)) for i in range(7)])
        h1 = packing.auto_pack(sc, time_budget=1.0)["height"]
        h2 = packing.auto_pack(sc, time_budget=0.3)["height"]   # kurzer Lauf: darf trotzdem nicht höher werden
        self.assertLessEqual(h2, h1 + 1e-6)
        self.assertEqual(sc.problems(), [])


if __name__ == "__main__":
    unittest.main()
