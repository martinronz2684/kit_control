"""Qt-Schicht: stellt AppCore der QML-Oberfläche als Objekt „backend“ zur Verfügung."""
from __future__ import annotations

import os
import subprocess
import sys
import threading

import numpy as np
import time

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from kitcontrol import updater
from kitcontrol.core import AppCore, TempLogger, documents_dir
from kitcontrol.version import __version__
from kitslice import profiles as PR
from kitslice.net import Pi
from kitslice.slicer import SliceCancelled


def _path(u) -> str:
    s = u.toString() if isinstance(u, QUrl) else str(u)
    return QUrl(s).toLocalFile() if s.startswith("file:") else s


class Backend(QObject):
    partsChanged = Signal()
    profilesChanged = Signal()
    sliceChanged = Signal()
    kitChanged = Signal()
    devicesChanged = Signal()
    jobsChanged = Signal()
    updateChanged = Signal()
    settingsChanged = Signal()
    piLayerReady = Signal("QVariant")
    message = Signal(str, str)          # Text, Art: info | ok | error

    def __init__(self):
        super().__init__()
        self.core = AppCore()
        self._slice_state = "idle"
        self._slice_progress = 0.0
        self._slice_error = ""
        self._cancel = False
        self._devices = []
        self._searching = False
        self._host = self.core.settings.get("host", "")
        self._connected = False
        self._kit = {}
        self._jobs = []
        self._update = ""
        self._update_progress = -1.0
        self._live_gen = 0
        self._log = TempLogger()
        self.message.connect(lambda *_: None)

    # -- Bauraum ---------------------------------------------------------------
    def _parts_changed(self):
        if self._slice_state in ("done", "error"):
            self._slice_state = "idle"
            self.sliceChanged.emit()
        self.partsChanged.emit()

    @Property("QVariant", notify=partsChanged)
    def parts(self):
        info = self.core.parts_info()
        try:                                     # Netze für die 3D-Ansicht auf der Grafikkarte bereitstellen
            from kitcontrol import geometry
            for p, d in zip(self.core.scene.parts, info):
                geometry.register(d["gkey"], p.mesh)
        except Exception:
            pass
        return info

    @Property("QVariant", notify=partsChanged)
    def problems(self):
        return self.core.problems()

    @Property("QVariant", notify=partsChanged)
    def notes(self):
        return self.core.notes()

    @Slot(int, result="QVariant")
    def partMesh(self, i):
        return self.core.display_mesh(i)

    @Property("QVariant", notify=settingsChanged)
    def ideal(self):
        from kitslice.scene import IDEAL_XY, IDEAL_Z
        return {"xy": IDEAL_XY, "z": IDEAL_Z}

    # -- Einstellungen (Zahnrad unten links) --------------------------------------
    DEFAULTS = {"lang": "de", "ideal_xy": 90.0, "ideal_z": 110.0, "pack_gap": 3.0, "pack_wall": 2.0,
                "check_updates": True, "auto_connect": True, "kit_laser_speed": 200.0, "notify": True,
                "theme": "dark"}

    @Property("QVariant", notify=settingsChanged)
    def settings(self):
        st = dict(self.DEFAULTS)
        st.update({k: v for k, v in self.core.settings.items() if k in self.DEFAULTS})
        st["est_learned"] = len(self.core.settings.get("est_history", []))
        st["est_factor"] = float(self.core.settings.get("est_factor", 1.0))
        return st

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key not in self.DEFAULTS:
            return
        d = self.DEFAULTS[key]
        try:
            value = type(d)(value) if not isinstance(d, bool) else bool(value)
        except (TypeError, ValueError):
            return
        self.core.save_settings(**{key: value})
        if key in ("ideal_xy", "ideal_z"):
            from kitslice.scene import set_ideal
            set_ideal(float(self.core.settings.get("ideal_xy", 90.0)), float(self.core.settings.get("ideal_z", 110.0)))
            self.partsChanged.emit()
        if key == "kit_laser_speed":
            self.sliceChanged.emit()
        self.settingsChanged.emit()

    @Slot()
    def resetIdeal(self):
        self.core.save_settings(ideal_xy=90.0, ideal_z=110.0)
        from kitslice.scene import set_ideal
        set_ideal(90.0, 110.0)
        self.partsChanged.emit()
        self.settingsChanged.emit()

    @Slot()
    def resetEstimate(self):
        self.core.save_settings(est_history=[], est_factor=1.0)
        self.sliceChanged.emit()
        self.settingsChanged.emit()
        self.message.emit("Druckzeit-Lernwerte zurückgesetzt", "ok")

    @Property(str, notify=settingsChanged)
    def lang(self):
        return self.core.settings.get("lang", "de")

    @Property("QVariant", constant=True)
    def translations(self):
        from kitcontrol import i18n
        return i18n.EN

    @Slot(str, result=str)
    def translate(self, text):
        from kitcontrol import i18n
        return i18n.translate(text, self.core.settings.get("lang", "de"))

    @Property(bool, notify=partsChanged)
    def canUndo(self):
        return bool(self.core.undo_stack)

    @Property(bool, notify=partsChanged)
    def canRedo(self):
        return bool(self.core.redo_stack)

    def _get_sel(self):
        return self.core.selected

    def _set_sel(self, i):
        if i != self.core.selected:
            self.core.selected = int(i)
            self.partsChanged.emit()

    selected = Property(int, _get_sel, _set_sel, notify=partsChanged)

    # -- Teileliste, nach gleichem Netz zusammengefasst ----------------------------
    def _thumb(self, p) -> str:
        """Kleines Vorschaubild (schräg von oben, schattiert) als data:-URL; je Netz einmal berechnet."""
        import base64
        import re as _re
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, Qt as _Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
        from kitslice.scene import mesh_uid
        key = mesh_uid(p.mesh)
        cache = self.__dict__.setdefault("_thumbs", {})
        if key in cache:
            return cache[key]
        t = p.simple(1800).astype(float)
        t = t - t.reshape(-1, 3).mean(axis=0)
        a, b = np.radians(-35), np.radians(30)              # Drehung um Z, dann Kippen
        rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
        v = t @ (rx @ rz).T
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        ln = np.linalg.norm(n, axis=1) + 1e-12
        light = np.abs(n @ np.array([0.3, 0.5, 0.8]) / ln)
        depth = v[:, :, 1].mean(axis=1)
        order = np.argsort(-depth)
        xy = v[:, :, [0, 2]]
        lo, hi = xy.reshape(-1, 2).min(axis=0), xy.reshape(-1, 2).max(axis=0)
        S = 56.0 / max(float((hi - lo).max()), 1e-6)
        img = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
        img.fill(_Qt.transparent)
        g = QPainter(img)
        g.setRenderHint(QPainter.Antialiasing)
        g.setPen(_Qt.NoPen)
        cx, cy = (lo + hi) / 2
        for i in order:
            k = 0.35 + 0.65 * float(light[i])
            g.setBrush(QColor(int(42 * k + 30), int(156 * k + 20), int(194 * k + 20)))
            g.drawPolygon(QPolygonF([QPointF(32 + (x - cx) * S, 32 - (y - cy) * S) for x, y in xy[i]]))
        g.end()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        url = "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()
        cache[key] = url
        return url

    @Property("QVariantList", notify=partsChanged)
    def partGroups(self):
        import re as _re
        from kitslice.scene import mesh_uid
        groups, order = {}, []
        sel = set(self.core.targets())
        for i, p in enumerate(self.core.scene.parts):
            key = f"{mesh_uid(p.mesh)}:{p.scale[0]:.4f}"
            if key not in groups:
                base = _re.sub(r"(\s\((Kopie|\d+)\))+$", "", p.name)
                try:
                    thumb = self._thumb(p)
                except Exception:
                    thumb = ""
                groups[key] = {"key": key, "name": base, "indices": [], "thumb": thumb,
                               "size": [round(float(v), 1) for v in sorted(p.size(), reverse=True)],
                               "locked": False, "status": ""}
                order.append(key)
            g = groups[key]
            g["indices"].append(i)
            g["locked"] = g["locked"] or bool(p.lock_pos or p.lock_orient)
        status = self.core.part_status()
        for g in groups.values():
            g["count"] = len(g["indices"])
            g["picked"] = all(i in sel for i in g["indices"])
            g["anyPicked"] = any(i in sel for i in g["indices"])
            st = [status.get(i, "") for i in g["indices"]]
            g["status"] = "overlap" if "overlap" in st else ("outside" if "outside" in st else "")
        return [groups[k] for k in order]

    @Slot(str)
    def groupAdd(self, key):
        for g in self.partGroups:
            if g["key"] == key:
                self.core.duplicate(g["indices"][-1])
                self._parts_changed()
                return

    @Slot(str)
    def groupRemove(self, key):
        for g in self.partGroups:
            if g["key"] == key:
                self.core.remove(g["indices"][-1])
                self._parts_changed()
                return

    @Property("QVariantList", notify=partsChanged)
    def layerFill(self):
        try:
            return self.core.layer_fill()
        except Exception:
            return []

    @Property("QVariantList", notify=partsChanged)
    def selection(self):
        return self.core.targets()

    @Slot(int, str)
    def selectPart(self, i, mode):
        self.core.select(int(i), mode or "set")
        self.partsChanged.emit()

    @Slot("QVariantList")
    def selectIndices(self, idx):
        self.core.select_many(idx)
        self.partsChanged.emit()

    @Slot()
    def selectAll(self):
        self.core.select_many(range(len(self.core.scene.parts)))
        self.partsChanged.emit()

    @Slot()
    def selectNone(self):
        self.core.select(-1)
        self.partsChanged.emit()

    @Slot()
    def removeSelected(self):
        self.core.remove_sel()
        self._parts_changed()

    @Slot()
    def duplicateSelected(self):
        self.core.duplicate_sel()
        self._parts_changed()

    @Slot()
    def rotateSelected(self):
        self.core.rotate_sel(90.0)
        self._parts_changed()

    @Slot()
    def layFlatSelected(self):
        self.core.lay_flat_sel()
        self._parts_changed()

    @Slot(str, bool)
    def lockSelected(self, key, value):
        self.core.lock_sel(key, value)
        self._parts_changed()

    @Slot(int, float, float, float)
    def moveSelected(self, lead, dx, dy, dz):
        self.core.move_sel(dx, dy, dz, int(lead))
        self._parts_changed()

    @Property(bool, constant=True)
    def gpuView(self):
        """3D-Ansicht auf der Grafikkarte, außer KIT_NO_GPU=1 oder Qt Quick 3D fehlt."""
        if os.environ.get("KIT_NO_GPU") == "1":
            return False
        try:
            import kitcontrol.geometry  # noqa: F401
            return True
        except Exception:
            return False

    @Property(float, constant=True)
    def plateMm(self):
        from kitslice.scene import PREFERRED_MM
        return PREFERRED_MM

    @Slot("QVariant")
    def addUrls(self, urls):
        paths = [_path(u) for u in (urls or [])]
        kcp = [p for p in paths if p.lower().endswith(".kcp")]
        if kcp:                                             # Projekt hineingezogen: öffnen
            self.loadProject(QUrl.fromLocalFile(kcp[0]).toString())
            paths = [p for p in paths if not p.lower().endswith(".kcp")]
            if not paths:
                return
        paths = [p for p in paths if p.lower().endswith(".stl")]
        if not paths:
            self.message.emit("Bitte STL-Dateien wählen", "error")
            return
        errs = self.core.add_files(paths)
        for e in errs:
            self.message.emit(e, "error")
        self._parts_changed()

    @Slot(int)
    def removePart(self, i):
        self.core.remove(i); self._parts_changed()

    @Slot()
    def clearParts(self):
        self.core.clear(); self._parts_changed()

    @Slot(int)
    def duplicatePart(self, i):
        self.core.duplicate(i); self._parts_changed()

    @Slot(int, str, "QVariant")
    def setPart(self, i, key, value):
        try:
            self.core.set_part(i, key, value if key.startswith("lock_") else float(value))
        except (TypeError, ValueError):
            return
        self._parts_changed()

    packChanged = Signal()

    @Property(str, notify=packChanged)
    def packState(self):
        return getattr(self, "_pack_state", "idle")

    @Property(float, notify=packChanged)
    def packProgress(self):
        return getattr(self, "_pack_progress", 0.0)

    @Property("QVariant", notify=partsChanged)
    def density(self):
        return self.core.density()

    def _pack_job(self, fn, done_msg):
        if getattr(self, "_pack_state", "idle") == "running":
            return
        self._pack_state, self._pack_progress, self._pack_cancel = "running", 0.0, False
        self.packChanged.emit()

        def prog(f):
            self._pack_progress = f
            self.packChanged.emit()

        def run():
            try:
                res = fn(prog, lambda: self._pack_cancel)
                self.message.emit(done_msg(res), "ok" if res is not False else "error")
            except Exception as e:
                self.message.emit(f"Anordnen fehlgeschlagen: {e}", "error")
            self._pack_state = "idle"
            self.packChanged.emit()
            self._parts_changed()
        threading.Thread(target=run, daemon=True, name="pack").start()

    @Slot("QVariant")
    def autoPack(self, opts):
        o = dict(opts or {})

        def fn(prog, cancel):
            return self.core.auto_pack(float(o.get("gap", 3)), float(o.get("wall", 2)), bool(o.get("rotate", True)),
                                       bool(o.get("onlySelected", False)), float(o.get("time", 8)), prog, cancel,
                                       quality=float(o.get("quality", 0.5)))

        def msg(r):
            if not r.get("ok"):
                return r.get("error") or f"Angeordnet, aber höher als der ideale Bereich ({r.get('height')} mm)"
            lk = f" – {r['locked']} gesperrte Teile wurden nicht bewegt" if r.get("locked") else ""
            return f"Angeordnet{lk}: Bauhöhe {r['height']} mm, Packdichte {r['density']} %, leere Schichten {r.get('empty_mm', 0)} mm ({r['passes']} Durchläufe)" + (
                " – Ausrichtungsregeln gelockert, weil die Teile sonst nicht passen" if r.get("relaxed") else "")
        self._pack_job(fn, msg)

    @Slot(int, "QVariant")
    def fillChamber(self, i, opts):
        o = dict(opts or {})

        def fn(prog, cancel):
            return self.core.fill(i, float(o.get("gap", 3)), float(o.get("wall", 2)), bool(o.get("rotate", True)), prog, cancel,
                                  quality=float(o.get("quality", 0.5)))
        self._pack_job(fn, lambda n: f"{n} Kopien hinzugefügt" if n else "Kein Platz für weitere Kopien")

    @Slot()
    def cancelPack(self):
        self._pack_cancel = True

    @Slot(float, float, float, float, float, float, result=int)
    def pickPart(self, ax, ay, az, bx, by, bz):
        return self.core.pick((ax, ay, az), (bx, by, bz))

    @Property(int, notify=partsChanged)
    def lockedCount(self):
        return sum(1 for p in self.core.scene.parts if p.lock_pos or p.lock_orient)

    @Slot()
    def addCalibrationPart(self):
        self.core.add_calibration_part()
        self._parts_changed()
        self.message.emit("Kalibrierteil hinzugefügt (40 × 40 × 5 mm, Nut hinten = Y) – drucken, außen messen, unter „Pulver“ eintragen", "ok")

    @Slot()
    def unlockAll(self):
        n = self.core.unlock_all()
        self._parts_changed()
        self.message.emit(f"Sperre bei {n} Teilen aufgehoben" if n else "Keine Teile gesperrt", "ok")

    @Slot(int, float, float, float)
    def movePart3(self, i, x, y, z):
        self.core.move_part(i, x, y, True, z)
        self._parts_changed()

    @Slot(int, float, float, bool)
    def movePart(self, i, x, y, record):
        self.core.move_part(i, x, y, record)
        self._parts_changed()

    @Slot(int)
    def layFlat(self, i):
        self.core.lay_flat(i); self._parts_changed()

    @Slot(str)
    def arrange(self, mode):
        if not self.core.arrange(mode or "nest"):
            self.message.emit("Nicht alle Bauteile passen in den idealen Druckbereich" if mode != "rows"
                              else "Nicht alle Bauteile passen nebeneinander auf die Platte", "error")
        self._parts_changed()

    @Slot()
    def undo(self):
        self.core.undo(); self._parts_changed()

    @Slot()
    def redo(self):
        self.core.redo(); self._parts_changed()

    @Slot("QVariant")
    def saveProject(self, url):
        try:
            p = _path(url)
            if not p.lower().endswith(".kcp"):
                p += ".kcp"
            self.core.save_project(p)
            self.recentChanged.emit()
            self.message.emit("Projekt gespeichert", "ok")
        except (OSError, ValueError) as e:
            self.message.emit(f"Speichern fehlgeschlagen: {e}", "error")

    recentChanged = Signal()

    @Property("QVariantList", notify=recentChanged)
    def recentProjects(self):
        return [r for r in self.core.settings.get("recent", []) if os.path.exists(r.get("path", ""))]

    @Slot("QVariant")
    def loadProject(self, url):
        try:
            self.core.load_project(_path(url))
            self.profilesChanged.emit()
            self._parts_changed()
            self.recentChanged.emit()
        except (OSError, ValueError, KeyError) as e:
            self.message.emit(f"Projekt lässt sich nicht öffnen: {e}", "error")

    @Slot("QVariant")
    def exportStl(self, url):
        try:
            p = _path(url)
            if not p.lower().endswith(".stl"):
                p += ".stl"
            self.core.export_stl(p)
            self.message.emit("STL exportiert", "ok")
        except (OSError, ValueError) as e:
            self.message.emit(f"Export fehlgeschlagen: {e}", "error")

    # -- Profile ---------------------------------------------------------------
    @Property("QVariant", notify=profilesChanged)
    def profiles(self):
        return PR.listing()

    @Property("QVariant", notify=profilesChanged)
    def profile(self):
        return self.core.profile()

    @Property(str, notify=profilesChanged)
    def profileId(self):
        return self.core.profile_id

    @Slot(str)
    def selectProfile(self, pid):
        try:
            self.core.set_profile(pid)
        except KeyError as e:
            self.message.emit(str(e), "error")
        self.profilesChanged.emit()
        self._parts_changed()

    @Slot("QVariant", result=str)
    def saveProfile(self, p):
        """Liefert eine Fehlermeldung oder einen leeren Text."""
        try:
            q = dict(p)
            for k in ("temps", "lamps", "shrink_pct"):
                if q.get(k) is not None:
                    q[k] = dict(q[k])
            if q.get("hatch_angles_deg") is not None:
                q["hatch_angles_deg"] = list(q["hatch_angles_deg"])
            self.core.save_profile(q)
        except (ValueError, KeyError, TypeError) as e:
            return str(e)
        self.profilesChanged.emit()
        self._parts_changed()
        self.message.emit("Profil gespeichert", "ok")
        return ""

    @Slot("QVariant", result=str)
    def applyProfile(self, p):
        """Wie saveProfile, aber ohne Meldung (für sofort übernommene Änderungen)."""
        try:
            q = dict(p)
            for k in ("temps", "lamps", "shrink_pct"):
                if q.get(k) is not None:
                    q[k] = dict(q[k])
            if q.get("hatch_angles_deg") is not None:
                q["hatch_angles_deg"] = list(q["hatch_angles_deg"])
            self.core.save_profile(q)
        except (ValueError, KeyError, TypeError) as e:
            return str(e)
        self.profilesChanged.emit()
        self._parts_changed()
        return ""

    @Slot(str)
    def newProfile(self, name):
        """Neues Material in der Liste: Kopie des gewählten Profils, sofort gespeichert und ausgewählt."""
        try:
            base = self.core.profile_id
            names = {p["name"] for p in PR.listing()}
            name = (name or "Neues Material").strip()
            n, k = name, 2
            while n in names:
                n, k = f"{name} {k}", k + 1
            self.core.save_profile(PR.derive(base, n))
        except (ValueError, KeyError) as e:
            self.message.emit(str(e), "error")
        self.profilesChanged.emit()
        self._parts_changed()

    @Slot(str)
    def deleteProfile(self, pid):
        try:
            PR.delete(pid)
            if self.core.profile_id == pid:
                self.core.set_profile("pa12")
        except (OSError, ValueError) as e:
            self.message.emit(str(e), "error")
        self.profilesChanged.emit()

    @Slot("QVariant")
    def importProfile(self, url):
        try:
            q = PR.import_file(_path(url))
            self.core.set_profile(q["id"])
            self.message.emit(f"Profil „{q['name']}“ importiert", "ok")
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.message.emit(f"Import fehlgeschlagen: {e}", "error")
        self.profilesChanged.emit()

    @Slot(str, "QVariant")
    def exportProfile(self, pid, url):
        try:
            p = _path(url)
            if not p.lower().endswith(".json"):
                p += ".json"
            PR.export(pid, p)
            self.message.emit("Profil exportiert", "ok")
        except (OSError, KeyError) as e:
            self.message.emit(f"Export fehlgeschlagen: {e}", "error")

    # -- Slicen ----------------------------------------------------------------
    @Property(str, notify=sliceChanged)
    def sliceState(self):
        return self._slice_state

    @Property(float, notify=sliceChanged)
    def sliceProgress(self):
        return self._slice_progress

    @Property(str, notify=sliceChanged)
    def sliceError(self):
        return self._slice_error

    @Property("QVariant", notify=sliceChanged)
    def estimate(self):
        return self.core.estimate() if self.core.job and self._slice_state == "done" else {}

    @Property("QVariant", notify=sliceChanged)
    def sliceMeta(self):
        return self.core.job[1] if self.core.job and self._slice_state == "done" else {}

    @Slot()
    def startSlice(self):
        if self._slice_state == "running":
            return
        if not self.core.scene.parts:
            self.message.emit("Bitte zuerst ein Bauteil hinzufügen", "error")
            return
        self._cancel = False
        self._slice_state, self._slice_progress, self._slice_error = "running", 0.0, ""
        self.sliceChanged.emit()
        last = [0.0]

        def prog(f):
            if f - last[0] >= 0.01 or f >= 1:
                last[0] = f
                self._slice_progress = f
                self.sliceChanged.emit()

        def run():
            try:
                self.core.slice(prog, lambda: self._cancel)
                self._slice_state = "done"
            except SliceCancelled:
                self._slice_state = "idle"
            except Exception as e:   # Meldung in der Oberfläche statt Absturz
                self._slice_state, self._slice_error = "error", str(e) or e.__class__.__name__
            self.sliceChanged.emit()
        threading.Thread(target=run, daemon=True, name="slice").start()

    @Slot()
    def cancelSlice(self):
        self._cancel = True

    @Slot(int, result="QVariant")
    def layer(self, n):
        return self.core.layer_preview(n) if self._slice_state == "done" else {}

    @Slot("QVariant")
    def saveJob(self, url):
        try:
            p = _path(url)
            if not p.lower().endswith(".bin"):
                p += ".bin"
            self.core.save_job(p)
            self.message.emit("Druckdatei gespeichert", "ok")
        except (OSError, ValueError) as e:
            self.message.emit(str(e), "error")

    # -- Kit ---------------------------------------------------------------------
    @Property("QVariant", notify=devicesChanged)
    def devices(self):
        return self._devices

    @Property(bool, notify=devicesChanged)
    def searching(self):
        return self._searching

    @Property(str, notify=kitChanged)
    def host(self):
        return self._host

    @Property(bool, notify=kitChanged)
    def connected(self):
        return self._connected

    @Property("QVariant", notify=kitChanged)
    def kit(self):
        return self._kit

    @Property("QVariant", notify=jobsChanged)
    def piJobs(self):
        return self._jobs

    @Slot()
    def discover(self):
        if self._searching:
            return
        self._searching = True
        self.devicesChanged.emit()

        def run():
            try:
                found = self.core.discover()
            except OSError:
                found = []
            self._devices, self._searching = found, False
            self.devicesChanged.emit()
            if found and not self._host:
                self.connectHost(found[0]["host"])
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def connectHost(self, host):
        host = host.strip()
        self._host = host
        self._connected = False
        self._kit = {}
        self.core.save_settings(host=host)
        self._live_gen += 1
        self.kitChanged.emit()
        if host:
            threading.Thread(target=self._live, args=(self._live_gen, host), daemon=True, name="live").start()

    def _live(self, gen, host):
        """Zustand vom Pi per Server-Sent Events; bei Abbruch alle 3 s neu verbinden."""
        pi = Pi(host, timeout=5)
        while gen == self._live_gen:
            try:
                first = pi.state()
                self._connected, self._kit = True, first
                self.kitChanged.emit()
                self.refreshJobs()
                for st in pi.events():
                    if gen != self._live_gen:
                        return
                    for k in ("current_job", "central", "pc_link", "transfer", "job_result"):
                        st.setdefault(k, self._kit.get(k))
                    changed_job = (st.get("current_job") or {}).get("id") != (self._kit.get("current_job") or {}).get("id")
                    prev = self._kit
                    self._kit = st
                    self._log.feed(st)
                    self._learn(prev, st)
                    self._track(prev, st)
                    self.kitChanged.emit()
                    if changed_job:
                        self.refreshJobs()
            except Exception:
                pass
            if gen != self._live_gen:
                return
            if self._connected:
                self._connected = False
                self.kitChanged.emit()
            time.sleep(3)

    # -- Live: Temperaturverlauf, Ereignisse, Druckverlauf ------------------------
    tempsChanged = Signal()
    historyChanged = Signal()

    def _track(self, prev, st):
        now = time.time()
        th = self.__dict__.setdefault("_temps", [])
        if not th or now - th[-1][0] >= 2.0:
            def f(v):
                try:
                    return round(float(v), 1)
                except (TypeError, ValueError):
                    return None
            th.append((now, f(st.get("surface")), f(st.get("chamber")),
                       f(st.get("target_surface_print")), f(st.get("target_chamber_print"))))
            del th[:-900]                                   # ca. 30 min
            self.tempsChanged.emit()
        name = ((prev.get("current_job") or {}).get("name") or (st.get("current_job") or {}).get("name") or "Job")
        if prev.get("countdown_on") and not st.get("countdown_on") and st.get("printing"):
            self.notify("Aufheizen fertig", f"{name}: der Druck startet")
        if prev.get("printing") and not st.get("printing"):
            done = (prev.get("percent") or 0) >= 95
            self.notify("Druck fertig" if done else "Druck beendet", f"{name} – {int(prev.get('percent') or 0)} %")
            hist = self.core.settings.get("history", [])
            hist.append({"name": name, "end": int(now), "duration_s": int(prev.get("elapsed_s") or 0),
                         "layers": int(prev.get("layer") or 0), "percent": int(prev.get("percent") or 0),
                         "result": "fertig" if done else "abgebrochen",
                         "profile": (prev.get("current_job") or {}).get("profile") or ""})
            self.core.save_settings(history=hist[-100:])
            self.historyChanged.emit()
        old = {e.get("code") for e in (prev.get("errors") or []) if isinstance(e, dict)}
        for e in st.get("errors") or []:
            if isinstance(e, dict) and e.get("code") not in old:
                self.notify("Fehler am Kit", f"{e.get('code', '')} {e.get('title', '')}".strip())

    @Property("QVariantList", notify=tempsChanged)
    def tempHistory(self):
        th = self.__dict__.get("_temps", [])
        t0 = th[-1][0] if th else 0
        return [[round(t - t0, 1), a, b, c, d] for t, a, b, c, d in th]

    @Property("QVariantList", notify=historyChanged)
    def printHistory(self):
        return list(reversed(self.core.settings.get("history", [])))

    @Slot()
    def clearHistory(self):
        self.core.save_settings(history=[])
        self.historyChanged.emit()

    tray = None

    @Slot(str, str)
    def notify(self, title, text):
        """Windows-Benachrichtigung (abschaltbar in den Einstellungen)."""
        from kitcontrol import i18n
        lang = self.core.settings.get("lang", "de")
        title, text = i18n.translate(title, lang), i18n.translate(text, lang)
        self.message.emit(f"{title}: {text}", "info")
        if self.tray is not None and self.core.settings.get("notify", True):
            try:
                self.tray.showMessage(title, text, self.tray.icon(), 10000)
            except Exception:
                pass

    def _learn(self, prev, st):
        """Laufzeit echter Drucke merken: Lasergeschwindigkeit und Schätzfaktor nachführen."""
        if st.get("laser_speed"):
            if abs(float(st["laser_speed"]) - float(self.core.settings.get("kit_laser_speed", 0) or 0)) > 0.5:
                self.core.save_settings(kit_laser_speed=float(st["laser_speed"]))
        if prev.get("printing") and not st.get("printing"):
            job = prev.get("current_job") or {}
            if job.get("id") and (prev.get("percent") or 0) >= 95:
                self.core.learn_print(job["id"], float(prev.get("elapsed_s") or 0), int(prev.get("layer") or 0))
                self.sliceChanged.emit()

    @Slot()
    def refreshJobs(self):
        host = self._host

        def run():
            try:
                self._jobs = Pi(host, timeout=5).jobs().get("jobs", [])
                self.jobsChanged.emit()
            except Exception:
                pass
        if host:
            threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def deletePiJob(self, job_id):
        host = self._host

        def run():
            try:
                r = Pi(host, timeout=8).delete_job(job_id)
            except Exception as e:
                r = {"ok": False, "error": str(e)}
            if r.get("ok"):
                self._jobs = [j for j in self._jobs if j.get("id") != job_id]
                self.jobsChanged.emit()
                self.message.emit("Job am Kit gelöscht", "ok")
            elif "not found" in str(r.get("error", "")):
                self.message.emit("Das Kit Control kann noch keine Jobs vom PC löschen – bitte am Pi updaten", "error")
            else:
                self.message.emit("Löschen fehlgeschlagen: " + str(r.get("error", "")), "error")
            self.refreshJobs()
        if host and job_id:
            threading.Thread(target=run, daemon=True).start()

    @Slot(bool)
    def send(self, start):
        if not self._host:
            self.message.emit("Kein Kit Control gewählt", "error")
            return
        if self._slice_state != "done":
            self.message.emit("Bitte zuerst slicen", "error")
            return
        host = self._host
        self.message.emit("Übertrage Job …", "info")

        def run():
            try:
                r = self.core.send(host, start)
            except Exception as e:
                r = {"ok": False, "error": str(e)}
            if r.get("ok") and r.get("job"):
                self.core.remember_sent(r["job"].get("id", ""))
            if not r.get("ok"):
                self.message.emit("Senden fehlgeschlagen: " + str(r.get("error", "")), "error")
            elif r.get("started"):
                self.message.emit("Job übertragen – Druck startet", "ok")
            elif start:
                self.message.emit("Job übertragen, aber nicht gestartet: " + r.get("start_error", ""), "error")
            else:
                self.message.emit("Job liegt in der Bibliothek am Kit", "ok")
            self.refreshJobs()
        threading.Thread(target=run, daemon=True).start()

    @Slot("QVariant")
    def cmd(self, c):
        """Bedienbefehl an den Pi (Heizen, Abbrechen, Pulver …)."""
        host, c = self._host, dict(c)

        def run():
            try:
                r = Pi(host, timeout=12).cmd(c)
            except Exception as e:
                r = {"ok": False, "error": str(e)}
            if r.get("ok"):
                self.message.emit("Ausgeführt", "ok")
            elif "Bedienung nur am Gerät" in str(r.get("error", "")):
                self.message.emit("Dieses Kit Control kennt den Schalter „Bedienung vom PC“ noch nicht – bitte am Pi updaten", "error")
            else:
                self.message.emit(str(r.get("error", "Fehler")), "error")
        if host:
            threading.Thread(target=run, daemon=True).start()

    @Slot()
    def powerOff(self):
        host = self._host

        def run():
            try:
                r = Pi(host, timeout=10).cmd({"cmd": "poweroff"})
            except Exception as e:
                r = {"ok": False, "error": str(e)}
            if r.get("ok"):
                self.message.emit("Kit Control fährt herunter – Strom trennen, sobald das Display schwarz ist (ca. 20 s)", "ok")
            elif "Nur am Kit Control" in str(r.get("error", "")) or "Bedienung nur am Gerät" in str(r.get("error", "")):
                self.message.emit("Dieses Kit Control kann noch nicht vom PC herunterfahren – bitte am Pi updaten", "error")
            else:
                self.message.emit(str(r.get("error", "Fehler")), "error")
        if host:
            threading.Thread(target=run, daemon=True).start()

    @Slot(str, int)
    def requestPiLayer(self, job_id, n):
        host = self._host

        def run():
            try:
                self.piLayerReady.emit(Pi(host, timeout=8).layer(job_id, n))
            except Exception:
                self.piLayerReady.emit({})
        if host and job_id:
            threading.Thread(target=run, daemon=True).start()

    # -- Update / System -----------------------------------------------------------
    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, notify=updateChanged)
    def updateVersion(self):
        return self._update

    @Property(float, notify=updateChanged)
    def updateProgress(self):
        return self._update_progress

    def check_update(self):
        def run():
            v = updater.check(__version__)
            if v:
                self._update = v
                self.updateChanged.emit()
        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def installUpdate(self):
        if self._update_progress >= 0:
            return
        self._update_progress = 0.0
        self.updateChanged.emit()

        def prog(f):
            self._update_progress = f
            self.updateChanged.emit()

        def run():
            try:
                path = updater.download(prog)
                updater.run_setup(path)
                os._exit(0)
            except Exception as e:
                self._update_progress = -1.0
                self.updateChanged.emit()
                self.message.emit(f"Update fehlgeschlagen: {e}", "error")
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def openFolder(self, which):
        from kitcontrol.core import data_dir
        d = {"logs": os.path.join(documents_dir(), "Temperaturprotokolle"),
             "profiles": PR.profile_dir(), "data": data_dir()}.get(which, documents_dir())
        os.makedirs(d, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(d)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", d])
