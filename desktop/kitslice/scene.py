"""Bauraum: Bauteile platzieren, drehen, skalieren und automatisch anordnen (wie Central „Placing“)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from kitslice import stl

# Kit: bevorzugter Bauraum 110 mm, maximal 130 mm (PrinterSpecKit), Ursprung in der Mitte
PREFERRED_MM = 110.0
MAX_MM = 130.0


@dataclass
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
    _cache: tuple = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: str, name: str | None = None) -> "Part":
        import os
        return cls(name or os.path.splitext(os.path.basename(path))[0], stl.load(path))

    def _oriented(self) -> np.ndarray:
        """Gedreht und skaliert, Mitte der Grundfläche im Ursprung, Unterseite auf z = 0."""
        key = (self.rot_x, self.rot_y, self.rot_z, tuple(self.scale))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        t = self.mesh * np.asarray(self.scale, dtype=float)
        t = t @ _rotation(self.rot_x, self.rot_y, self.rot_z).T
        lo, hi = t.reshape(-1, 3).min(axis=0), t.reshape(-1, 3).max(axis=0)
        t = t - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        self._cache = (key, t)
        return t

    def placed(self) -> np.ndarray:
        return self._oriented() + np.array([self.x, self.y, self.z_lift])

    def size(self):
        t = self._oriented().reshape(-1, 3)
        return tuple(t.max(axis=0) - t.min(axis=0))

    def bbox(self):
        t = self.placed().reshape(-1, 3)
        return tuple(t.min(axis=0)), tuple(t.max(axis=0))

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

    def merged(self) -> np.ndarray:
        if not self.parts:
            raise ValueError("Keine Bauteile im Bauraum")
        return np.concatenate([p.placed() for p in self.parts])

    def problems(self) -> list[str]:
        """Bauteile außerhalb des Bauraums oder überlappend (Querschnitte werden verschmolzen)."""
        msgs = []
        h = self.size_mm / 2
        boxes = []
        for p in self.parts:
            lo, hi = p.bbox()
            if lo[0] < -h - 1e-6 or lo[1] < -h - 1e-6 or hi[0] > h + 1e-6 or hi[1] > h + 1e-6:
                msgs.append(f"{p.name}: liegt außerhalb des Bauraums ({self.size_mm:g} mm)")
            if hi[2] > MAX_MM:
                msgs.append(f"{p.name}: höher als {MAX_MM:g} mm")
            boxes.append((p.name, lo, hi))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if all(a[1][k] < b[2][k] and b[1][k] < a[2][k] for k in range(3)):
                    msgs.append(f"{a[0]} und {b[0]} überlappen")
        return msgs

    def arrange(self, gap: float = 3.0) -> bool:
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
        return ok
