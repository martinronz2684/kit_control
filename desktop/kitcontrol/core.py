"""Logik der Desktop-App ohne Qt: Bauraum, Rückgängig, Profile, Slicen, Projekt, Verbindung zum Pi.

Die Qt-Schicht (backend.py) ruft nur diese Klasse auf – so lässt sich alles ohne Oberfläche testen.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import sys
import threading
import time

import numpy as np

from kitslice.scene import mesh_uid

import kitslice  # noqa: F401  (setzt den Pfad zu kitctl)
from kitslice import profiles as PR
from kitslice import stl
from kitslice.job import make_job
from kitslice.net import Pi, discover
from kitslice.scene import PREFERRED_MM, Part, Scene

PART_KEYS = ("x", "y", "rot_x", "rot_y", "rot_z", "scale", "z_lift", "lock_pos", "lock_orient")


def data_dir() -> str:
    if sys.platform == "win32":
        d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "KitControl")
    else:
        d = os.path.join(os.path.expanduser("~/.config"), "kitcontrol")
    os.makedirs(d, exist_ok=True)
    return d


def documents_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), "Documents", "KitControl")
    os.makedirs(d, exist_ok=True)
    return d


def hull(xy: np.ndarray) -> list:
    """Konvexe Hülle (Andrew) – Umriss eines Bauteils in der Draufsicht."""
    pts = np.unique(np.round(xy, 2), axis=0)
    if len(pts) < 3:
        return pts.tolist()
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(pts), half(pts[::-1])
    return [[float(a), float(b)] for a, b in lo[:-1] + up[:-1]]


def decimate(tris: np.ndarray, max_tris: int) -> list:
    """Netz für die Anzeige vereinfachen: nahe Eckpunkte zusammenlegen (Mittelwert statt Rasterpunkt,
    damit nichts „treppig“ aussieht), bis höchstens max_tris Dreiecke übrig sind."""
    t = tris
    if len(t) > max_tris:
        pts = t.reshape(-1, 3)
        size = float(np.max(pts.max(axis=0) - pts.min(axis=0))) or 1.0
        cell = size / 1500
        for _ in range(16):
            q = np.floor(pts / cell).astype(np.int64)
            _, inv = np.unique(q, axis=0, return_inverse=True)
            inv = inv.ravel()
            f = inv.reshape(-1, 3)
            keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
            if keep.sum() <= max_tris:
                cnt = np.bincount(inv)
                mean = np.zeros((len(cnt), 3))
                np.add.at(mean, inv, pts)
                mean /= cnt[:, None]
                t = mean[f[keep]]
                break
            cell *= 1.25
        else:
            t = t[:: len(t) // max_tris + 1]
    return np.round(t.astype(np.float64), 3).ravel().tolist()


def quat(R: np.ndarray) -> list:
    """Rotationsmatrix -> Quaternion [w, x, y, z]."""
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    return [float(w), float(x), float(y), float(z)]


class AppCore:
    def __init__(self):
        self.scene = Scene()
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.selected = -1
        self.multi: list[int] = []          # Mehrfachauswahl (Strg+Klick, Rahmen); leer = nur self.selected
        self.settings = self._load_settings()
        self.profile_id = self.settings.get("profile", "pa12")
        from kitslice.scene import set_ideal
        set_ideal(float(self.settings.get("ideal_xy", 90.0)), float(self.settings.get("ideal_z", 110.0)))
        try:
            PR.get(self.profile_id)
        except KeyError:
            self.profile_id = "pa12"
        self.job = None            # (bytes, meta, layers)
        self.slice_error = ""
        self.last_pack = None
        self._outline_cache = {}

    # -- Einstellungen ---------------------------------------------------------
    def _settings_file(self):
        return os.path.join(data_dir(), "settings.json")

    def _load_settings(self) -> dict:
        try:
            with open(self._settings_file(), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_settings(self, **kw) -> None:
        self.settings.update(kw)
        try:
            with open(self._settings_file(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError:
            pass

    # -- Bauraum ---------------------------------------------------------------
    def _snapshot(self):
        return [(p.name, p.mesh, {k: getattr(p, k) for k in PART_KEYS}) for p in self.scene.parts], self.selected

    def _restore(self, snap):
        self.multi = []
        parts, sel = snap
        self.scene.parts = []
        for name, mesh, kw in parts:
            p = Part(name, mesh)
            for k, v in kw.items():
                setattr(p, k, v)
            self.scene.parts.append(p)
        self.selected = sel if sel < len(self.scene.parts) else len(self.scene.parts) - 1
        self.job = None

    def _push(self):
        self.undo_stack.append(self._snapshot())
        del self.undo_stack[:-50]
        self.redo_stack.clear()
        self.job = None

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())
        return True

    def add_files(self, paths: list[str]) -> list[str]:
        """STL-Dateien laden und automatisch anordnen. Liefert Fehlermeldungen."""
        errs, new = [], []
        for path in paths:
            try:
                new.append(Part.load(path))
            except (OSError, ValueError) as e:
                errs.append(f"{os.path.basename(path)}: {e}")
        if new:
            self._push()
            for p in new:
                self.scene.add(p)
            self.scene.nest(only=new)
            self.selected = len(self.scene.parts) - 1
            self.multi = []
        return errs

    # -- Auswahl (eine oder mehrere) ---------------------------------------------
    def targets(self) -> list[int]:
        n = len(self.scene.parts)
        m = sorted({i for i in self.multi if 0 <= i < n})
        if len(m) > 1:
            return m
        return [self.selected] if 0 <= self.selected < n else []

    def select(self, i: int, mode: str = "set") -> None:
        n = len(self.scene.parts)
        if not 0 <= i < n:
            self.selected, self.multi = -1, []
            return
        cur = set(self.targets())
        if mode == "toggle":
            cur ^= {i}
            self.multi = sorted(cur)
            self.selected = i if i in cur else (self.multi[-1] if self.multi else -1)
        elif mode == "add":
            cur.add(i)
            self.multi, self.selected = sorted(cur), i
        else:
            self.multi, self.selected = [], i

    def select_many(self, idx) -> None:
        n = len(self.scene.parts)
        idx = sorted({int(i) for i in idx if 0 <= int(i) < n})
        self.multi = idx
        self.selected = idx[-1] if idx else -1

    def remove_sel(self) -> None:
        t = self.targets()
        if not t:
            return
        self._push()
        for i in sorted(t, reverse=True):
            del self.scene.parts[i]
        self.multi, self.selected = [], -1

    def duplicate_sel(self) -> None:
        t = self.targets()
        if not t:
            return
        self._push()
        new = []
        for i in t:
            src = self.scene.parts[i]
            p = Part(src.name + " (Kopie)", src.mesh)
            for k in PART_KEYS:
                setattr(p, k, copy.copy(getattr(src, k)))
            p.lock_pos = False
            self.scene.add(p)
            new.append(p)
        self.scene.nest(only=new)
        n = len(self.scene.parts)
        self.select_many(range(n - len(new), n))

    def rotate_sel(self, deg: float = 90.0) -> None:
        t = self.targets()
        if not t:
            return
        self._push()
        for i in t:
            p = self.scene.parts[i]
            if not p.lock_orient:
                p.rot_z = (p.rot_z + deg) % 360
                p._cache = None

    def lay_flat_sel(self) -> None:
        t = self.targets()
        if not t:
            return
        self._push()
        for i in t:
            if not self.scene.parts[i].lock_orient:
                self.scene.parts[i].lay_flat()

    def lock_sel(self, key: str, value: bool) -> None:
        if key not in ("lock_pos", "lock_orient"):
            return
        t = self.targets()
        if t:
            self._push()
            for i in t:
                setattr(self.scene.parts[i], key, bool(value))

    def move_sel(self, dx: float, dy: float, dz: float = 0.0, lead: int = -1) -> None:
        """Ziehen mit der Maus: alle ausgewählten Teile um denselben Weg verschieben (ein Rückgängig-Schritt)."""
        t = self.targets()
        if lead >= 0 and lead not in t:
            t = [lead]
        if not t:
            return
        self._push()
        for i in t:
            p = self.scene.parts[i]
            p.x, p.y = float(p.x + dx), float(p.y + dy)
            p.z_lift = max(0.0, float(p.z_lift + dz))
        self.job = None

    def remove(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            del self.scene.parts[i]
            self.selected = min(self.selected, len(self.scene.parts) - 1)
            self.multi = []

    def clear(self) -> None:
        if self.scene.parts:
            self._push()
            self.scene.parts = []
            self.selected = -1
            self.multi = []

    def duplicate(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            src = self.scene.parts[i]
            p = Part(src.name + " (Kopie)", src.mesh)
            for k in PART_KEYS:
                setattr(p, k, copy.copy(getattr(src, k)))
            p.lock_pos = False                  # eine Kopie liegt woanders – Positionssperre nicht mitkopieren
            self.scene.add(p)
            self.scene.nest(only=[p])
            self.selected = len(self.scene.parts) - 1
            self.multi = []

    def set_part(self, i: int, key: str, value) -> None:
        if not 0 <= i < len(self.scene.parts) or key not in PART_KEYS + ("scale_pct",):
            return
        p = self.scene.parts[i]
        self._push()
        if key in ("lock_pos", "lock_orient"):
            setattr(p, key, bool(value))
        elif key == "scale_pct":
            f = max(1.0, min(1000.0, float(value))) / 100.0
            p.scale = (f, f, f)
        else:
            setattr(p, key, float(value))
        p._cache = None

    def pick(self, a, b) -> int:
        """Strahl von a nach b (Slicer-Koordinaten) -> Index des vordersten getroffenen Teils, sonst -1."""
        a = np.asarray(a, float)
        d = np.asarray(b, float) - a
        best, bi = np.inf, -1
        for i, p in enumerate(self.scene.parts):
            lo, hi = (np.asarray(v, float) for v in p.bbox())
            with np.errstate(divide="ignore", invalid="ignore"):
                t1, t2 = (lo - 1 - a) / d, (hi + 1 - a) / d
            tn, tf = np.nanmax(np.minimum(t1, t2)), np.nanmin(np.maximum(t1, t2))
            if not tf >= max(tn, 0) or tn >= best:
                continue
            t = p.light(6000)
            v0, e1, e2 = t[:, 0], t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
            h = np.cross(d, e2)
            det = np.einsum("ij,ij->i", e1, h)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            sv = a - v0
            u = np.einsum("ij,ij->i", sv, h) * inv
            q = np.cross(sv, e1)
            v = (q @ d) * inv
            tt = np.einsum("ij,ij->i", e2, q) * inv
            hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (tt > 0)
            if hit.any():
                tmin = float(tt[hit].min())
                if tmin < best:
                    best, bi = tmin, i
        return bi

    def add_calibration_part(self) -> None:
        """Kalibrierteil wie bei Sintratec: Rahmen 40 × 40 mm, innen 30 × 30 mm offen, 5 mm hoch;
        oben auf dem hinteren Steg (Y-Seite) eine Nut 5 mm breit, 1 mm tief als Richtungsmarke.
        Soll: X 40, Y 40, Z 5 mm (innen 30 mm)."""
        def extrude(loops, rects, z0, z1):
            """Geschlossener Körper: Seitenwände nur am Rand (loops, außen gegen, Löcher im Uhrzeigersinn),
            Deckel/Boden aus Rechtecken – keine inneren Flächen (sonst Laserlinien mitten im Teil)."""
            t = []
            for loop in loops:
                for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]):
                    t += [[(x0, y0, z0), (x1, y1, z0), (x1, y1, z1)], [(x0, y0, z0), (x1, y1, z1), (x0, y0, z1)]]
            for x0, y0, x1, y1 in rects:
                t += [[(x0, y0, z1), (x1, y0, z1), (x1, y1, z1)], [(x0, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                      [(x0, y0, z0), (x1, y1, z0), (x1, y0, z0)], [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0)]]
            return np.array(t, float)
        ring = [[(0, 0), (40, 0), (40, 40), (0, 40)], [(5, 5), (5, 35), (35, 35), (35, 5)]]
        ring_rects = [(0, 0, 40, 5), (0, 5, 5, 35), (35, 5, 40, 35), (0, 35, 40, 40)]
        c_loop = [[(0, 0), (40, 0), (40, 40), (22.5, 40), (22.5, 35), (35, 35), (35, 5), (5, 5), (5, 35),
                   (17.5, 35), (17.5, 40), (0, 40)]]
        c_rects = [(0, 0, 40, 5), (0, 5, 5, 35), (35, 5, 40, 35), (0, 35, 17.5, 40), (22.5, 35, 40, 40)]
        mesh = np.concatenate([extrude(ring, ring_rects, 0, 4), extrude(c_loop, c_rects, 4, 5)])
        self._push()
        p = Part("Kalibrierteil 40 × 40 × 5 mm", mesh)
        self.scene.add(p)
        self.scene.nest(only=[p])
        self.selected = len(self.scene.parts) - 1
        self.multi = []

    def unlock_all(self) -> int:
        n = sum(1 for p in self.scene.parts if p.lock_pos or p.lock_orient)
        if n:
            self._push()
            for p in self.scene.parts:
                p.lock_pos = p.lock_orient = False
        return n

    def move_part(self, i: int, x: float, y: float, record: bool, z=None) -> None:
        """Ziehen mit der Maus: nur am Anfang einen Rückgängig-Schritt anlegen."""
        if not 0 <= i < len(self.scene.parts):
            return
        if record:
            self._push()
        p = self.scene.parts[i]
        p.x, p.y = float(x), float(y)
        if z is not None:
            p.z_lift = max(0.0, float(z))
        self.job = None

    def lay_flat(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            self.scene.parts[i].lay_flat()

    def arrange(self, mode: str = "nest", gap: float = 3.0) -> bool:
        """mode: nest = 3D-Nesting im idealen Bereich, rows = nebeneinander auf der Platte."""
        if not self.scene.parts:
            return True
        self._push()
        return self.scene.arrange_rows(gap) if mode == "rows" else self.scene.nest(gap)

    def auto_pack(self, gap=3.0, wall=2.0, rotate=True, only_selected=False, time_budget=8.0,
                  progress=None, cancel=None, quality=0.5) -> dict:
        """Intelligentes Auto-Anordnen (siehe kitslice.packing)."""
        from kitslice import packing
        if not self.scene.parts:
            return {"ok": True, "height": 0, "density": 0, "passes": 0}
        self._push()
        only = [self.scene.parts[self.selected]] if only_selected and 0 <= self.selected < len(self.scene.parts) else None
        r = packing.auto_pack(self.scene, gap, wall, rotate, only, time_budget=time_budget,
                              progress=progress, cancel=cancel, quality_w=quality)
        r["locked"] = sum(1 for p in self.scene.parts if p.lock_pos)
        self.last_pack = r
        return r

    def fill(self, i: int, gap=3.0, wall=2.0, rotate=True, progress=None, cancel=None, quality=0.5) -> int:
        from kitslice import packing
        if not self.scene.parts:
            return 0
        if not 0 <= i < len(self.scene.parts):
            i = 0                       # ohne Auswahl: das (erste) Teil auffüllen
        self.selected = i
        self.multi = []
        self._push()
        return packing.fill(self.scene, self.scene.parts[i], gap, wall, rotate, progress=progress, cancel=cancel,
                            quality_w=quality)

    def density(self) -> dict:
        from kitslice.packing import volume
        from kitslice.scene import IDEAL_XY  # noqa: F401  (aktueller Wert, siehe set_ideal)
        from kitslice import scene as _sc
        IDEAL_XY = _sc.IDEAL_XY
        if not self.scene.parts:
            return {"height": 0.0, "density": 0.0}
        h = float(max(p.bbox()[1][2] for p in self.scene.parts))
        v = sum(volume(p) for p in self.scene.parts)
        return {"height": round(h, 1), "density": round(v / (IDEAL_XY * IDEAL_XY * max(h, 1e-6)) * 100, 1)}

    def display_mesh(self, i: int, max_tris: int = 0) -> list:
        """Vereinfachtes Netz eines Bauteils für die 3D-Ansicht (flach: x,y,z je Ecke, lokal zur Lage)."""
        if not 0 <= i < len(self.scene.parts):
            return []
        p = self.scene.parts[i]
        if not max_tris:   # Gesamtbudget für flüssiges Drehen auf alle Teile verteilen
            max_tris = int(max(1500, min(16000, 40000 / max(1, len(self.scene.parts)))))
        key = ("mesh", mesh_uid(p.mesh), p.rot_x, p.rot_y, p.rot_z, tuple(p.scale), max_tris)
        if key not in self._outline_cache:
            self._outline_cache[key] = np.round(p.transform(p.simple(max_tris)), 3).ravel().tolist()
        return self._outline_cache[key]

    def layer_fill(self, step: float = 1.0) -> list:
        """Belegung je Höhe (Anteil des idealen Bereichs in %, je `step` mm) – zeigt leere oder sehr volle Schichten."""
        from kitslice import scene as _sc
        from kitslice.scene import _columns
        if not self.scene.parts:
            return []
        res = 1.0
        top = max(float(p.bbox()[1][2]) for p in self.scene.parts)
        n = int(np.ceil(top / step)) + 1
        diff = np.zeros(n + 2)
        for p in self.scene.parts:
            key = ("fill", p.rot_x, p.rot_y, p.rot_z, tuple(p.scale), p.x, p.y, p.z_lift)
            cc = p.__dict__.setdefault("_fillcache", {})
            if key not in cc:
                cc.clear()
                cols = _columns(p.light(6000), res)
                lohi = np.array(list(cols.values()), float) if cols else np.zeros((0, 2))
                cc[key] = lohi
            lohi = cc[key]
            if not len(lohi):
                continue
            a = np.clip(np.floor(lohi[:, 0] / step).astype(int), 0, n)
            b = np.clip(np.ceil(lohi[:, 1] / step).astype(int), 0, n)
            np.add.at(diff, a, res * res)
            np.add.at(diff, b, -res * res)
        area = np.cumsum(diff)[:n - 1]
        return [round(float(v) / (_sc.IDEAL_XY ** 2) * 100, 1) for v in area]

    def part_status(self) -> dict:
        """Je Teil: overlap / outside (für Farben in der 3D-Ansicht)."""
        st = {}
        try:
            for i, j in self.scene.collision_pairs():
                st[i] = st[j] = "overlap"
            for i in self.scene.outside():
                st.setdefault(i, "outside")
        except Exception:
            pass
        return st

    def parts_info(self) -> list[dict]:
        out = []
        status = self.part_status()
        multi = set(self.targets())
        for i, p in enumerate(self.scene.parts):
            sx, sy, sz = p.size()
            key = (mesh_uid(p.mesh), p.rot_x, p.rot_y, p.rot_z, tuple(p.scale))
            if key not in self._outline_cache:
                t = p.transform(p.simple(3000)).reshape(-1, 3)
                if len(t) > 60000:
                    t = t[:: len(t) // 60000 + 1]
                self._outline_cache[key] = hull(t[:, :2])
            from kitslice.scene import _rotation
            origin = p.transform(np.zeros((1, 3)))[0]          # wohin der Original-Nullpunkt wandert
            out.append({
                "gkey": f"m{mesh_uid(p.mesh)}",
                "quat": quat(_rotation(p.rot_x, p.rot_y, p.rot_z)),
                "pos": [float(p.x + origin[0]), float(p.y + origin[1]), float(p.z_lift + origin[2])],
                "scale3": [float(v) for v in p.scale],
                "mesh_key": f"{mesh_uid(p.mesh)}:{p.rot_x}:{p.rot_y}:{p.rot_z}:{p.scale[0]}",
                "z": round(float(p.z_lift), 2),
                "index": i, "name": p.name, "x": round(float(p.x), 2), "y": round(float(p.y), 2),
                "rot_x": float(p.rot_x), "rot_y": float(p.rot_y), "rot_z": float(p.rot_z),
                "scale_pct": round(float(p.scale[0]) * 100, 1),
                "size": [round(float(sx), 2), round(float(sy), 2), round(float(sz), 2)], "outline": self._outline_cache[key],
                "triangles": int(len(p.mesh)),
                "lock_pos": bool(p.lock_pos), "lock_orient": bool(p.lock_orient),
                "status": status.get(i, ""), "picked": i in multi,
            })
        return out

    def problems(self) -> list[str]:
        return self.scene.problems()

    def notes(self) -> list[str]:
        return self.scene.notes()

    # -- Projekt ---------------------------------------------------------------
    def _remember_recent(self, path: str) -> None:
        import time as _t
        rec = [r for r in self.settings.get("recent", []) if r.get("path") != path]
        rec.insert(0, {"path": path, "name": os.path.splitext(os.path.basename(path))[0], "time": int(_t.time()),
                       "parts": len(self.scene.parts)})
        self.save_settings(recent=rec[:8])

    def save_project(self, path: str) -> None:
        data = {"format": "kitcontrol-project", "version": 1, "profile": self.profile_id, "parts": []}
        for p in self.scene.parts:
            data["parts"].append({
                "name": p.name, **{k: getattr(p, k) for k in PART_KEYS},
                "mesh": base64.b64encode(p.mesh.astype("<f4").tobytes()).decode(),
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self._remember_recent(path)

    def load_project(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") != "kitcontrol-project":
            raise ValueError("Keine Kit-Control-Projektdatei")
        self._push()
        self.scene.parts = []
        for d in data["parts"]:
            mesh = np.frombuffer(base64.b64decode(d["mesh"]), dtype="<f4").astype(np.float64).reshape(-1, 3, 3)
            from kitslice.scene import share_mesh
            p = Part(d["name"], share_mesh(mesh))
            for k in PART_KEYS:
                if k in d:
                    setattr(p, k, tuple(d[k]) if k == "scale" else d[k])
            self.scene.parts.append(p)
        if data.get("profile"):
            try:
                PR.get(data["profile"])
                self.profile_id = data["profile"]
            except KeyError:
                pass
        self.selected = 0 if self.scene.parts else -1
        self.multi = []
        self._remember_recent(path)

    def export_stl(self, path: str) -> None:
        stl.save_binary(self.scene.merged(), path)

    # -- Profile ---------------------------------------------------------------
    def profile(self) -> dict:
        return PR.get(self.profile_id)

    def set_profile(self, pid: str) -> None:
        PR.get(pid)
        if pid != self.profile_id:
            self.profile_id = pid
            self.job = None
            self.save_settings(profile=pid)

    def save_profile(self, p: dict) -> dict:
        q = PR.save(p)
        self.set_profile(q["id"])
        self.job = None
        return q

    # -- Slicen ----------------------------------------------------------------
    def slice(self, progress=None, cancel=None) -> dict:
        self.job = None
        data, meta, layers = make_job(self.scene, self.profile(), progress, cancel)
        meta["powder_mm"] = round(meta["height_mm"] + 5.0, 1)      # Pulver laden: Bauhöhe + 5 mm
        meta["parts_cm3"] = round(self.parts_volume_cm3(), 3)
        self.job = (data, meta, layers)
        return meta

    MATERIAL_KEYS = ("price_eur_kg", "bulk_g_ml", "part_g_cm3")

    def material(self, pid: str | None = None) -> dict:
        """Preis und Dichten eines Materials: Werte aus dem Profil, in den Einstellungen änderbar
        (auch bei den schreibgeschützten Vorlagen)."""
        pid = pid or self.profile_id
        try:
            p = PR.get(pid)
        except Exception:
            p = {}
        m = {"price_eur_kg": p.get("price_eur_kg"), "bulk_g_ml": p.get("bulk_g_ml") or 0.6,
             "part_g_cm3": p.get("part_g_cm3") or 0.95}
        m.update({k: v for k, v in self.settings.get("materials", {}).get(pid, {}).items() if k in self.MATERIAL_KEYS})
        return m

    def set_material(self, key: str, value, pid: str | None = None) -> None:
        if key not in self.MATERIAL_KEYS:
            raise ValueError(key)
        pid = pid or self.profile_id
        v = None if value in (None, "") else float(value)
        lim = {"price_eur_kg": (0.0, 10000.0), "bulk_g_ml": (0.05, 3.0), "part_g_cm3": (0.05, 3.0)}[key]
        if v is not None and not lim[0] <= v <= lim[1]:
            raise ValueError(f"{lim[0]:g}–{lim[1]:g} erlaubt")
        mats = dict(self.settings.get("materials", {}))
        m = dict(mats.get(pid, {}))
        m[key] = v
        mats[pid] = m
        self.save_settings(materials=mats)

    def parts_volume_cm3(self) -> float:
        """Volumen aller Bauteile (geschlossene Netze, in cm³)."""
        vol = 0.0
        for p in self.scene.parts:
            t = p._oriented()
            vol += abs(float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)
        return vol / 1000.0

    def powder(self, meta: dict | None = None) -> dict:
        """Pulver einfüllen (Vorrat = Bauraumfläche × Pulverhöhe), Gewicht in den Teilen und Kosten."""
        meta = meta or (self.job[1] if self.job else None)
        if not meta:
            return {}
        m = self.material()
        area_cm2 = (self.scene.size_mm / 10.0) ** 2
        fill_ml = area_cm2 * meta.get("powder_mm", 0.0) / 10.0
        parts_cm3 = meta.get("parts_cm3", 0.0)
        out = {"fill_l": fill_ml / 1000.0, "fill_g": fill_ml * m["bulk_g_ml"], "parts_cm3": parts_cm3,
               "parts_g": parts_cm3 * m["part_g_cm3"], "price_eur_kg": m["price_eur_kg"],
               "bulk_g_ml": m["bulk_g_ml"], "part_g_cm3": m["part_g_cm3"]}
        if m["price_eur_kg"]:
            out["parts_eur"] = out["parts_g"] / 1000.0 * m["price_eur_kg"]
            out["fill_eur"] = out["fill_g"] / 1000.0 * m["price_eur_kg"]
        return out

    def laser_speed(self) -> float:
        """Für die Zeitschätzung: Profilwert, sonst zuletzt am Kit gesehene Geschwindigkeit, sonst 200 mm/s."""
        v = self.profile().get("laser_speed_mm_s")
        return float(v or self.settings.get("kit_laser_speed") or 200.0)

    def estimate(self, meta: dict | None = None) -> dict:
        from kitslice.job import estimate_seconds
        meta = meta or (self.job[1] if self.job else None)
        if not meta:
            return {}
        f = float(self.settings.get("est_factor", 1.0))
        secs = estimate_seconds(meta, self.laser_speed(), float(self.settings.get("est_recoat_s", 10.0)),
                                float(self.settings.get("est_jump_mm_s", 2000.0)), f)
        return {"seconds": round(secs), "laser_mm_s": self.laser_speed(), "learned": len(self.settings.get("est_history", []))}

    def learn_print(self, job_id: str, elapsed_s: float, layers_done: int) -> None:
        """Nach einem Druck: Schätzfaktor aus gemessener Zeit nachführen (gleitender Mittelwert)."""
        sent = self.settings.get("sent_jobs", {}).get(job_id)
        if not sent or layers_done < 20 or elapsed_s <= 0:
            return
        pred = sent["seconds"] / max(1.0, float(self.settings.get("est_factor", 1.0)))   # ohne Faktor
        pred_done = pred * min(1.0, layers_done / max(1, sent["layers"]))
        if pred_done <= 0:
            return
        ratio = elapsed_s / pred_done
        f = float(self.settings.get("est_factor", 1.0))
        hist = (self.settings.get("est_history", []) + [round(ratio, 3)])[-10:]
        f = 0.5 * f + 0.5 * ratio if len(hist) > 1 else ratio
        sj = dict(self.settings.get("sent_jobs", {}))
        sj.pop(job_id, None)
        self.save_settings(est_factor=round(max(0.2, min(5.0, f)), 3), est_history=hist, sent_jobs=sj)

    def remember_sent(self, job_id: str) -> None:
        est = self.estimate()
        if job_id and est and self.job:
            sj = dict(self.settings.get("sent_jobs", {}))
            sj[job_id] = {"seconds": est["seconds"], "layers": self.job[1]["layers"]}
            self.save_settings(sent_jobs=dict(list(sj.items())[-20:]))

    def layer_preview(self, n: int, max_infill: int = 9000) -> dict:
        if not self.job:
            return {}
        layers = self.job[2]
        n = max(1, min(len(layers), int(n)))
        L = layers[n - 1]
        cont = []
        for c in L.contours:
            pts = np.vstack([c, c[:1]])
            seg = np.hstack([pts[:-1], pts[1:]])
            cont.extend(np.round(seg, 3).ravel().tolist())
        h = L.hatches
        step = max(1, len(h) // max_infill + (1 if len(h) % max_infill else 0)) if len(h) > max_infill else 1
        inf = np.round(np.asarray(h[::step]), 3).ravel().tolist() if len(h) else []
        return {"layer": n, "z": round(L.z, 3), "contour": cont, "infill": inf, "count": len(layers)}

    def save_job(self, path: str) -> None:
        if not self.job:
            raise ValueError("Noch nicht geslict")
        with open(path, "wb") as f:
            f.write(self.job[0])

    def job_name(self) -> str:
        names = [p.name for p in self.scene.parts]
        base = names[0] if names else "Job"
        return base + (f" +{len(names) - 1}" if len(names) > 1 else "")

    # -- Kit / Pi --------------------------------------------------------------
    @staticmethod
    def discover() -> list[dict]:
        return discover()

    def send(self, host: str, start: bool) -> dict:
        if not self.job:
            raise ValueError("Bitte zuerst slicen")
        prof = self.profile()
        return Pi(host).send_job(self.job[0], self.job_name(), prof, start)


class TempLogger:
    """Wie Central: während des Drucks jede Minute Datum;Schicht;Oberfläche;Kammer als CSV."""

    def __init__(self):
        self.path = None
        self.last = 0.0
        self.lock = threading.Lock()

    def feed(self, st: dict) -> None:
        with self.lock:
            if not st.get("printing"):
                self.path = None
                return
            now = time.time()
            if self.path is None:
                d = os.path.join(documents_dir(), "Temperaturprotokolle")
                os.makedirs(d, exist_ok=True)
                name = ((st.get("current_job") or {}).get("name") or "Druck").replace("/", "-").replace("\\", "-")
                self.path = os.path.join(d, time.strftime("%Y-%m-%d_%H-%M_") + name[:40] + ".csv")
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write("Datum und Zeit;Schicht;Oberflächentemperatur;Kammertemperatur\n")
                self.last = 0.0
            if now - self.last < 60:
                return
            self.last = now
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%d.%m.%Y %H:%M:%S')};{st.get('layer', '')};"
                            f"{st.get('surface', '')};{st.get('chamber', '')}\n")
            except OSError:
                pass
