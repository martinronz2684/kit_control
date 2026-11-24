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

import kitslice  # noqa: F401  (setzt den Pfad zu kitctl)
from kitslice import profiles as PR
from kitslice import stl
from kitslice.job import make_job
from kitslice.net import Pi, discover
from kitslice.scene import PREFERRED_MM, Part, Scene

PART_KEYS = ("x", "y", "rot_x", "rot_y", "rot_z", "scale", "z_lift")


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


class AppCore:
    def __init__(self):
        self.scene = Scene()
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.selected = -1
        self.settings = self._load_settings()
        self.profile_id = self.settings.get("profile", "pa12")
        try:
            PR.get(self.profile_id)
        except KeyError:
            self.profile_id = "pa12"
        self.job = None            # (bytes, meta, layers)
        self.slice_error = ""
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
            self.scene.arrange()
            self.selected = len(self.scene.parts) - 1
        return errs

    def remove(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            del self.scene.parts[i]
            self.selected = min(self.selected, len(self.scene.parts) - 1)

    def clear(self) -> None:
        if self.scene.parts:
            self._push()
            self.scene.parts = []
            self.selected = -1

    def duplicate(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            src = self.scene.parts[i]
            p = Part(src.name + " (Kopie)", src.mesh)
            for k in PART_KEYS:
                setattr(p, k, copy.copy(getattr(src, k)))
            self.scene.add(p)
            self.scene.arrange()
            self.selected = len(self.scene.parts) - 1

    def set_part(self, i: int, key: str, value) -> None:
        if not 0 <= i < len(self.scene.parts) or key not in PART_KEYS + ("scale_pct",):
            return
        p = self.scene.parts[i]
        self._push()
        if key == "scale_pct":
            f = max(1.0, min(1000.0, float(value))) / 100.0
            p.scale = (f, f, f)
        else:
            setattr(p, key, float(value))
        p._cache = None

    def move_part(self, i: int, x: float, y: float, record: bool) -> None:
        """Ziehen mit der Maus: nur am Anfang einen Rückgängig-Schritt anlegen."""
        if not 0 <= i < len(self.scene.parts):
            return
        if record:
            self._push()
        p = self.scene.parts[i]
        p.x, p.y = float(x), float(y)
        self.job = None

    def lay_flat(self, i: int) -> None:
        if 0 <= i < len(self.scene.parts):
            self._push()
            self.scene.parts[i].lay_flat()

    def arrange(self) -> bool:
        if not self.scene.parts:
            return True
        self._push()
        return self.scene.arrange()

    def parts_info(self) -> list[dict]:
        out = []
        for i, p in enumerate(self.scene.parts):
            sx, sy, sz = p.size()
            key = (id(p.mesh), p.rot_x, p.rot_y, p.rot_z, tuple(p.scale))
            if key not in self._outline_cache:
                t = p._oriented().reshape(-1, 3)
                if len(t) > 60000:
                    t = t[:: len(t) // 60000 + 1]
                self._outline_cache[key] = hull(t[:, :2])
            out.append({
                "index": i, "name": p.name, "x": round(float(p.x), 2), "y": round(float(p.y), 2),
                "rot_x": float(p.rot_x), "rot_y": float(p.rot_y), "rot_z": float(p.rot_z),
                "scale_pct": round(float(p.scale[0]) * 100, 1),
                "size": [round(float(sx), 2), round(float(sy), 2), round(float(sz), 2)], "outline": self._outline_cache[key],
                "triangles": int(len(p.mesh)),
            })
        return out

    def problems(self) -> list[str]:
        return self.scene.problems()

    # -- Projekt ---------------------------------------------------------------
    def save_project(self, path: str) -> None:
        data = {"format": "kitcontrol-project", "version": 1, "profile": self.profile_id, "parts": []}
        for p in self.scene.parts:
            data["parts"].append({
                "name": p.name, **{k: getattr(p, k) for k in PART_KEYS},
                "mesh": base64.b64encode(p.mesh.astype("<f4").tobytes()).decode(),
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def load_project(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") != "kitcontrol-project":
            raise ValueError("Keine Kit-Control-Projektdatei")
        self._push()
        self.scene.parts = []
        for d in data["parts"]:
            mesh = np.frombuffer(base64.b64decode(d["mesh"]), dtype="<f4").astype(np.float64).reshape(-1, 3, 3)
            p = Part(d["name"], mesh)
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
        self.job = (data, meta, layers)
        return meta

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
        inf = np.round(np.asarray(h[::step]), 3).ravel().tolist() if h else []
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
