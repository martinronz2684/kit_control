"""Bauraum: Bauteile platzieren, drehen, skalieren und automatisch anordnen (wie Central „Placing“)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from kitslice import stl

# Kit: bevorzugter Bauraum 110 mm, maximal 130 mm (PrinterSpecKit), Ursprung in der Mitte.
# Idealer Druckbereich (gleichmäßigste Temperatur): 90 x 90 x 110 mm.
PREFERRED_MM = 110.0
MAX_MM = 130.0
IDEAL_XY = 90.0
IDEAL_Z = 110.0


def set_ideal(xy: float, z: float) -> None:
    """Idealen Druckbereich ändern (Einstellungen). Wirkt auf Hinweise, Anordnen und Anzeige."""
    global IDEAL_XY, IDEAL_Z
    IDEAL_XY = float(min(max(xy, 20.0), PREFERRED_MM))
    IDEAL_Z = float(min(max(z, 10.0), MAX_MM))
GRID = 1.0           # Raster für Nesting und Kollisionsprüfung (mm)


_MESHCACHE: dict = {}      # id(Netz) -> (Netz, {Schlüssel: Wert}) – geteilt von Kopien desselben Teils


def mesh_cache(mesh: np.ndarray) -> dict:
    ent = _MESHCACHE.get(id(mesh))
    if ent is None or ent[0] is not mesh:
        if len(_MESHCACHE) > 200:
            _MESHCACHE.clear()
        ent = (mesh, {})
        _MESHCACHE[id(mesh)] = ent
    return ent[1]


_UID = [0]
_SHARED: dict = {}                 # Inhalt (Hash) -> Netz: gleiche Datei mehrfach geladen = ein Netz


def share_mesh(mesh: np.ndarray) -> np.ndarray:
    """Gleiche Netze (z. B. dieselbe STL mehrfach hinzugefügt) zu einem Objekt zusammenführen – dann
    teilen sich alle Kopien Anzeige, Vereinfachung und Packberechnung (sonst alles einzeln, sehr langsam)."""
    import hashlib
    import weakref
    key = (mesh.shape, hashlib.blake2b(np.ascontiguousarray(mesh, dtype=np.float32).tobytes(), digest_size=16).hexdigest())
    ref = _SHARED.get(key)
    m = ref() if ref is not None else None
    if m is not None:
        return m
    try:
        _SHARED[key] = weakref.ref(mesh)
    except TypeError:
        return mesh
    return mesh


def mesh_uid(mesh: np.ndarray) -> int:
    """Eindeutige, nie wiederverwendete Nummer eines Netzes (id() kann nach dem Löschen neu vergeben werden)."""
    c = mesh_cache(mesh)
    if "uid" not in c:
        _UID[0] += 1
        c["uid"] = _UID[0]
    return c["uid"]


def mesh_bounds(mesh: np.ndarray):
    c = mesh_cache(mesh)
    if "bounds" not in c:
        pts = mesh.reshape(-1, 3)
        c["bounds"] = (pts.min(axis=0), pts.max(axis=0))
    return c["bounds"]


def mesh_verts(mesh: np.ndarray):
    c = mesh_cache(mesh)
    if "verts" not in c:
        c["verts"] = np.unique(mesh.reshape(-1, 3), axis=0)
    return c["verts"]


@dataclass(eq=False)
class Part:
    name: str
    mesh: np.ndarray                         # Original-Dreiecke (n, 3, 3)
    x: float = 0.0                           # Lage der Mitte der Grundfläche
    y: float = 0.0
    rot_z: float = 0.0                       # Grad
    rot_x: float = 0.0
    rot_y: float = 0.0
    scale: tuple = (1.0, 1.0, 1.0)
    z_lift: float = 0.0                      # Abstand zur Bauplatte (mm)
    lock_pos: bool = False                   # beim Auto-Anordnen liegen lassen
    lock_orient: bool = False                # beim Auto-Anordnen nicht drehen
    _cache: tuple = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: str, name: str | None = None) -> "Part":
        import os
        return cls(name or os.path.splitext(os.path.basename(path))[0], share_mesh(stl.load(path)))

    def _oriented(self) -> np.ndarray:
        """Gedreht und skaliert, Mitte der Grundfläche im Ursprung, Unterseite auf z = 0."""
        key = (self.rot_x, self.rot_y, self.rot_z, tuple(self.scale))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        t = self.mesh * np.asarray(self.scale, dtype=float)
        t = t @ _rotation(self.rot_x, self.rot_y, self.rot_z).T
        lo, hi = t.reshape(-1, 3).min(axis=0), t.reshape(-1, 3).max(axis=0)
        t = t - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        if len(t) <= 150_000:                    # große Netze nicht je Teil im Speicher halten
            self._cache = (key, t)
        return t

    def placed(self) -> np.ndarray:
        return self._oriented() + np.array([self.x, self.y, self.z_lift])

    def transform(self, pts: np.ndarray, rot=None) -> np.ndarray:
        """Gleiche Drehung/Skalierung/Zentrierung wie _oriented() auf andere Punkte anwenden
        (z. B. auf ein vereinfachtes Netz). rot = (rx, ry, rz) statt der aktuellen Drehung."""
        rx, ry, rz = rot if rot is not None else (self.rot_x, self.rot_y, self.rot_z)
        R = _rotation(rx, ry, rz)
        sc = np.asarray(self.scale, dtype=float)
        key = ("bb", rx, ry, rz, tuple(self.scale))
        cache = self.__dict__.setdefault("_bbcache", {})
        if key not in cache:
            if all(abs(a % 90) < 1e-9 for a in (rx, ry, rz)):
                # 90°-Drehungen: Hüllquader = gedrehte Ecken des Original-Hüllquaders (exakt, sofort)
                lo0, hi0 = mesh_bounds(self.mesh)
                v = np.array([[x, y, z] for x in (lo0[0], hi0[0]) for y in (lo0[1], hi0[1]) for z in (lo0[2], hi0[2])])
            else:
                v = mesh_verts(self.mesh)
            r = (v * sc) @ R.T
            lo, hi = r.min(axis=0), r.max(axis=0)
            cache[key] = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        return (pts * sc) @ R.T - cache[key]

    def simple(self, max_tris: int = 6000) -> np.ndarray:
        """Vereinfachtes Originalnetz (einmal berechnet) – für Packen und Anzeige."""
        cache = mesh_cache(self.mesh)
        if ("simple", max_tris) not in cache:
            cache[("simple", max_tris)] = simplify_mesh(self.mesh, max_tris)
        return cache[("simple", max_tris)]

    def obox(self):
        """Hüllquader im gedrehten, zentrierten System (ohne das volle Netz zu drehen)."""
        key = ("ob", self.rot_x, self.rot_y, self.rot_z, tuple(self.scale))
        cache = self.__dict__.setdefault("_bbcache", {})
        if key not in cache:
            R = _rotation(self.rot_x, self.rot_y, self.rot_z)
            sc = np.asarray(self.scale, dtype=float)
            if all(abs(a % 90) < 1e-9 for a in (self.rot_x, self.rot_y, self.rot_z)):
                lo0, hi0 = mesh_bounds(self.mesh)
                v = np.array([[x, y, z] for x in (lo0[0], hi0[0]) for y in (lo0[1], hi0[1]) for z in (lo0[2], hi0[2])])
            else:
                v = mesh_verts(self.mesh)
            r = (v * sc) @ R.T
            lo, hi = r.min(axis=0), r.max(axis=0)
            off = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
            cache[key] = (lo - off, hi - off)
        return cache[key]

    def size(self):
        lo, hi = self.obox()
        return tuple(float(v) for v in hi - lo)

    def bbox(self):
        lo, hi = self.obox()
        p = np.array([self.x, self.y, self.z_lift])
        return tuple(float(v) for v in lo + p), tuple(float(v) for v in hi + p)

    def light(self, max_tris: int = 6000) -> np.ndarray:
        """Vereinfachtes Netz in aktueller Lage (für Prüfungen, Packen, Anzeige)."""
        return self.transform(self.simple(max_tris)) + np.array([self.x, self.y, self.z_lift])

    def lay_flat(self) -> None:
        """Größte ebene Fläche nach unten drehen (wie „auf Fläche legen“)."""
        t = self.mesh
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        a = np.linalg.norm(n, axis=1)
        nn = n / np.maximum(a, 1e-12)[:, None]
        key = np.round(nn, 3)
        uniq, inv = np.unique(key, axis=0, return_inverse=True)
        best = uniq[np.argmax(np.bincount(inv.ravel(), weights=a))]
        # Rotation so, dass best nach -Z zeigt; auf rot_x/rot_y abbilden
        bx, by, bz = best / np.linalg.norm(best)
        self.rot_x = math.degrees(math.atan2(by, -bz)) if abs(by) > 1e-9 or bz > 0 else 0.0
        r = _rotation(self.rot_x, 0, 0) @ np.array([bx, by, bz])
        self.rot_y = -math.degrees(math.atan2(r[0], -r[2])) if abs(r[0]) > 1e-9 else 0.0
        self._cache = None


def simplify_mesh(tris: np.ndarray, max_tris: int) -> np.ndarray:
    """Nahe Eckpunkte zusammenlegen (Mittelwert), bis höchstens max_tris Dreiecke übrig sind."""
    if len(tris) <= max_tris:
        return tris
    pts = tris.reshape(-1, 3)
    size = float(np.max(pts.max(axis=0) - pts.min(axis=0))) or 1.0
    cell = size / (np.sqrt(max_tris) * 3.0)
    for _ in range(24):
        q = np.floor(pts / cell).astype(np.int64)
        key = (q[:, 0] * 73856093) ^ (q[:, 1] * 19349663) ^ (q[:, 2] * 83492791)
        _, inv = np.unique(key, return_inverse=True)
        inv = inv.ravel()
        f = inv.reshape(-1, 3)
        keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
        if keep.sum() <= max_tris:
            cnt = np.bincount(inv)
            mean = np.zeros((len(cnt), 3))
            np.add.at(mean, inv, pts)
            mean /= cnt[:, None]
            return mean[f[keep]]
        cell *= 1.3
    return tris[:: len(tris) // max_tris + 1]


def _rotation(rx: float, ry: float, rz: float) -> np.ndarray:
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


@dataclass
class Scene:
    parts: list = field(default_factory=list)
    size_mm: float = PREFERRED_MM

    def add(self, part: Part) -> Part:
        self.parts.append(part)
        return part

    def indexed(self):
        """Alle Bauteile als ein indiziertes Netz (Eckpunkte, Dreiecke) – ohne Dreiecksuppe im Speicher.
        Kopien desselben Teils teilen sich die Indizierung des Originalnetzes."""
        if not self.parts:
            raise ValueError("Keine Bauteile im Bauraum")
        from kitslice.stl import index as index_mesh
        vs, fs, off = [], [], 0
        for p in self.parts:
            c = mesh_cache(p.mesh)
            if "index" not in c:
                v0, f0 = index_mesh(p.mesh)
                c["index"] = (v0, f0.astype(np.int32))
            v0, f0 = c["index"]
            vs.append(p.transform(v0) + np.array([p.x, p.y, p.z_lift]))
            fs.append(f0 + off)
            off += len(v0)
        return np.concatenate(vs), np.concatenate(fs).astype(np.int64 if off > 2**31 - 1 else np.int32)

    def merged(self) -> np.ndarray:
        if not self.parts:
            raise ValueError("Keine Bauteile im Bauraum")
        return np.concatenate([p.placed() for p in self.parts])

    def problems(self) -> list[str]:
        """Harte Fehler: außerhalb des Bauraums (110 mm) oder Bauteile durchdringen sich."""
        msgs = []
        h = self.size_mm / 2
        for p in self.parts:
            lo, hi = p.bbox()
            if lo[0] < -h - 1e-6 or lo[1] < -h - 1e-6 or hi[0] > h + 1e-6 or hi[1] > h + 1e-6:
                msgs.append(f"{p.name}: liegt außerhalb des Bauraums ({self.size_mm:g} mm)")
            if hi[2] > MAX_MM:
                msgs.append(f"{p.name}: höher als {MAX_MM:g} mm")
        for a, b in self.collisions():
            msgs.append(f"{a} und {b} überlappen")
        return msgs

    def notes(self) -> list[str]:
        """Hinweise: außerhalb des idealen Druckbereichs 90 x 90 x 110 mm."""
        out = []
        hx = IDEAL_XY / 2
        for p in self.parts:
            lo, hi = p.bbox()
            if lo[0] < -hx - 1e-6 or lo[1] < -hx - 1e-6 or hi[0] > hx + 1e-6 or hi[1] > hx + 1e-6 or hi[2] > IDEAL_Z + 1e-6:
                out.append(f"{p.name}: außerhalb des idealen Druckbereichs ({IDEAL_XY:g} × {IDEAL_XY:g} × {IDEAL_Z:g} mm)")
        return out

    def collisions(self, tol: float = 0.05) -> list[tuple[str, str]]:
        """Paare, deren Säulen (je Rasterzelle unterste bis oberste Fläche) sich in der Höhe überschneiden."""
        out = []
        boxes = [p.bbox() for p in self.parts]
        cols = {}
        for i in range(len(self.parts)):
            for j in range(i + 1, len(self.parts)):
                a, b = boxes[i], boxes[j]
                if not all(a[0][k] < b[1][k] - tol and b[0][k] < a[1][k] - tol for k in range(3)):
                    continue
                for k in (i, j):
                    if k not in cols:
                        q = self.parts[k]
                        key = ("cols", q.rot_x, q.rot_y, q.rot_z, tuple(q.scale), q.x, q.y, q.z_lift)
                        cc = q.__dict__.setdefault("_colcache", {})
                        if key not in cc:
                            cc.clear()
                            cc[key] = _columns(q.light(12000), 0.5)   # fein genug auch für 1 mm Abstand
                        cols[k] = cc[key]
                ca, cb = cols[i], cols[j]
                common = set(ca) & set(cb)
                if any(max(ca[c][0], cb[c][0]) < min(ca[c][1], cb[c][1]) - tol for c in common):
                    out.append((self.parts[i].name, self.parts[j].name))
        return out

    def arrange(self, gap: float = 3.0) -> bool:
        """Standard: 3D-Nesting im idealen Druckbereich."""
        return self.nest(gap)

    def arrange_rows(self, gap: float = 3.0) -> bool:
        """Grundflächen in Reihen anordnen (größte zuerst), Gesamtbild in der Mitte. False, wenn es nicht passt."""
        if not self.parts:
            return True
        lim = self.size_mm
        items = sorted(self.parts, key=lambda p: -p.size()[1])
        rows, row, x, y, rh = [], [], 0.0, 0.0, 0.0
        for p in items:
            w, d, _ = p.size()
            if row and x + w > lim:
                rows.append((row, y, rh))
                y += rh + gap
                row, x, rh = [], 0.0, 0.0
            row.append((p, x, w, d))
            x += w + gap
            rh = max(rh, d)
        rows.append((row, y, rh))
        total_h = y + rh
        ok = total_h <= lim + 1e-6 and all(r[-1][1] + r[-1][2] <= lim + 1e-6 for r, _, _ in rows)
        for r, ry, rh in rows:
            rw = r[-1][1] + r[-1][2]
            for p, px, w, d in r:
                p.x = px + w / 2 - rw / 2
                p.y = -(ry + d / 2 - total_h / 2)
                p.z_lift = 0.0
        return ok

    def nest(self, gap: float = 3.0, area: float | None = None, height: float | None = None,
             res: float = GRID, rotations=(0, 90, 180, 270), progress=None, only=None) -> bool:
        """Teile in den idealen Bereich packen (3D-Voxelraster, siehe kitslice.packing).
        only: nur diese Teile platzieren (z. B. nach „Hinzufügen“), ohne sie zu drehen."""
        from kitslice import packing
        area = IDEAL_XY if area is None else area
        height = IDEAL_Z if height is None else height
        r = packing.auto_pack(self, gap=gap, wall=2.0, allow_rotation=only is None, only=only,
                              area=area, height=height, time_budget=0.0 if only is not None else 2.0,
                              progress=progress)
        return bool(r.get("ok"))

def _samples(tris: np.ndarray, step: float) -> np.ndarray:
    """Punkte auf allen Dreiecken im Abstand von höchstens etwa step (für die Rasterung)."""
    e = np.maximum.reduce([np.linalg.norm(tris[:, 1] - tris[:, 0], axis=1),
                           np.linalg.norm(tris[:, 2] - tris[:, 1], axis=1),
                           np.linalg.norm(tris[:, 0] - tris[:, 2], axis=1)])
    k = np.clip(np.ceil(e / step).astype(int), 1, 96)
    out = [tris.reshape(-1, 3)]
    for kk in np.unique(k):
        sel = tris[k == kk]
        if kk == 1:
            continue
        a, b = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1))
        m = a + b <= kk
        w1, w2 = a[m] / kk, b[m] / kk
        w0 = 1 - w1 - w2
        pts = (sel[:, None, 0] * w0[None, :, None] + sel[:, None, 1] * w1[None, :, None]
               + sel[:, None, 2] * w2[None, :, None])
        out.append(pts.reshape(-1, 3))
    return np.concatenate(out)


def _profile(tris: np.ndarray, res: float):
    """Unterste und oberste Fläche je Rasterzelle (NaN = leer) samt Lage der Zelle (0, 0) in mm."""
    pts = _samples(tris, res * 0.7)
    mx, my = float(pts[:, 0].min()), float(pts[:, 1].min())
    ix = np.floor((pts[:, 0] - mx) / res - 1e-6).clip(0).astype(int)
    iy = np.floor((pts[:, 1] - my) / res - 1e-6).clip(0).astype(int)
    w, h = ix.max() + 1, iy.max() + 1
    bot = np.full((h, w), np.inf)
    top = np.full((h, w), -np.inf)
    np.minimum.at(bot, (iy, ix), pts[:, 2])
    np.maximum.at(top, (iy, ix), pts[:, 2])
    empty = ~np.isfinite(bot)
    # Innenflächen ohne Treffer (sehr große Dreiecke) füllen: Zeile für Zeile zwischen erstem und letztem Treffer
    for r in range(h):
        hit = np.flatnonzero(~empty[r])
        if len(hit) > 1:
            gaps = np.flatnonzero(empty[r, hit[0]:hit[-1]]) + hit[0]
            if len(gaps):
                bot[r, gaps] = np.interp(gaps, hit, bot[r, hit])
                top[r, gaps] = np.interp(gaps, hit, top[r, hit])
    if not np.isfinite(bot).any():
        return None
    return bot, np.where(np.isfinite(top), top, np.nan), mx, my


def _dilate(H: np.ndarray, g: int) -> np.ndarray:
    """Maximum über die Nachbarschaft (Quadrat mit Radius g) – seitlicher Abstand beim Nesting."""
    if g <= 0:
        return H
    out = H.copy()
    n0, n1 = H.shape
    for dy in range(-g, g + 1):
        for dx in range(-g, g + 1):
            if dx * dx + dy * dy > g * g + g:
                continue
            ys, yd = (slice(dy, n0), slice(0, n0 - dy)) if dy >= 0 else (slice(0, n0 + dy), slice(-dy, n0))
            xs, xd = (slice(dx, n1), slice(0, n1 - dx)) if dx >= 0 else (slice(0, n1 + dx), slice(-dx, n1))
            np.maximum(out[yd, xd], H[ys, xs], out=out[yd, xd])
    return out


def _columns(tris: np.ndarray, res: float) -> dict:
    """{(ix, iy): (z_unten, z_oben)} im globalen Raster – für die Kollisionsprüfung."""
    pts = _samples(tris, res * 0.7)
    ix = np.floor(pts[:, 0] / res).astype(np.int64)
    iy = np.floor(pts[:, 1] / res).astype(np.int64)
    key = ix * 100003 + iy
    order = np.argsort(key)
    key, z = key[order], pts[order, 2]
    uniq, start = np.unique(key, return_index=True)
    lo = np.minimum.reduceat(z, start)
    hi = np.maximum.reduceat(z, start)
    return dict(zip(uniq.tolist(), zip(lo.tolist(), hi.tolist())))
