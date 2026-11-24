"""Netz schneiden und Schichten aufbauen (Kontur + Schraffur) – nach den Regeln aus Central."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from kitslice import polygon as G
from kitslice.stl import index as index_mesh


class SliceCancelled(Exception):
    pass


@dataclass
class Layer:
    z: float                                    # Schnittebene in mm
    contours: list = field(default_factory=list)   # Polylinien (n, 2), geschlossen gezeichnet
    hatches: list = field(default_factory=list)    # Strecken (x0, y0, x1, y1)

    @property
    def empty(self) -> bool:
        return not self.contours and not self.hatches


def cross_sections(tris: np.ndarray, layer_mm: float, progress=None, cancel=None):
    """Schnitte in der Mitte jeder Schicht: z = (i + 0.5) * Schichtdicke, i = 0 .. n-1.
    Liefert eine Liste von Querschnitten (Liste von Polygonen, noch nicht ausgerichtet)."""
    verts, faces = index_mesh(tris)
    zmin = verts[:, 2].min()
    if zmin < -1e-6:
        raise ValueError("Bauteil liegt unter der Bauplatte")
    vz = verts[:, 2]
    fz = vz[faces]
    fmin, fmax = fz.min(axis=1), fz.max(axis=1)
    n = max(1, int(math.ceil(vz.max() / layer_mm - 1e-9)))
    order = np.argsort(fmin)
    fmin_sorted = fmin[order]
    out = []
    for i in range(n):
        if cancel and cancel():
            raise SliceCancelled()
        z = (i + 0.5) * layer_mm
        cand = order[: np.searchsorted(fmin_sorted, z, side="right")]
        act = cand[fmax[cand] > z]
        out.append(_section(verts, faces[act], z) if len(act) else [])
        if progress and (i % 10 == 0 or i == n - 1):
            progress(0.6 * (i + 1) / n)
    return out


def _section(verts, faces, z):
    above = verts[faces, 2] >= z                                  # (m, 3); Punkte auf der Ebene zählen als oben
    edges = []
    pts = {}
    for a, b in ((0, 1), (1, 2), (2, 0)):
        cross = above[:, a] != above[:, b]
        va, vb = faces[:, a], faces[:, b]
        lo, hi = np.minimum(va, vb), np.maximum(va, vb)
        key = lo * (len(verts) + 1) + hi
        edges.append(np.where(cross, key, -1))
        sel = np.flatnonzero(cross)
        if len(sel):
            p, q = verts[lo[sel]], verts[hi[sel]]
            t = (z - p[:, 2]) / (q[:, 2] - p[:, 2])
            xy = p[:, :2] + (q[:, :2] - p[:, :2]) * t[:, None]
            for kk, v in zip(key[sel].tolist(), xy):
                pts[kk] = v
    e = np.stack(edges, axis=1)
    # je Dreieck genau zwei geschnittene Kanten -> ein Segment zwischen zwei Kantenpunkten
    adj: dict[int, list[int]] = {}
    for row in e.tolist():
        k = [v for v in row if v >= 0]
        if len(k) != 2:
            continue
        adj.setdefault(k[0], []).append(k[1])
        adj.setdefault(k[1], []).append(k[0])
    loops = []
    seen = set()
    for start in adj:
        if start in seen:
            continue
        chain = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = [v for v in adj[cur] if v != prev and v not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            chain.append(cur)
        if len(chain) >= 3:
            loops.append(np.array([pts[k] for k in chain]))
    return loops


@dataclass
class SliceSettings:
    layer_mm: float = 0.1
    perimeters: int = 1
    perimeter_offset_mm: float = 0.2
    draw_original_boundary: bool = False
    hatch_offset_mm: float = 0.25
    hatch_spacing_mm: float = 0.12
    hatch_angles_deg: tuple = (45.0, -45.0, -135.0, 135.0)
    alternating: bool = True
    min_vector_mm: float = 0.025

    @classmethod
    def from_profile(cls, p: dict) -> "SliceSettings":
        return cls(
            layer_mm=p["layer_um"] / 1000.0,
            perimeters=int(p["perimeters"]),
            perimeter_offset_mm=p["perimeter_offset_um"] / 1000.0,
            draw_original_boundary=bool(p.get("draw_original_boundary", False)),
            hatch_offset_mm=p["hatch_offset_um"] / 1000.0,
            hatch_spacing_mm=p["hatch_spacing_um"] / 1000.0,
            hatch_angles_deg=tuple(p.get("hatch_angles_deg") or (45.0, -45.0, -135.0, 135.0)),
            alternating=bool(p.get("alternating_hatch", True)),
            min_vector_mm=p.get("min_vector_um", 25) / 1000.0,
        )


def build_layers(sections, s: SliceSettings, progress=None, cancel=None) -> list[Layer]:
    layers = []
    n = len(sections)
    angles = [math.radians(a) for a in s.hatch_angles_deg] or [0.0]
    for i, sec in enumerate(sections):
        if cancel and cancel():
            raise SliceCancelled()
        z = (i + 0.5) * s.layer_mm
        L = Layer(z)
        if sec:
            loops = [G.simplify(l, s.min_vector_mm) for l in sec]
            loops = G.orient([l for l in loops if len(l) >= 3])
            if loops:
                if s.draw_original_boundary:
                    L.contours += loops
                cur = loops
                for _ in range(s.perimeters):               # Perimeter nacheinander, außen zuerst
                    cur = G.offset(cur, s.perimeter_offset_mm)
                    L.contours += cur
                infill = G.offset(loops, s.hatch_offset_mm)  # Füllversatz vom Originalrand
                L.hatches = G.hatch(infill, s.hatch_spacing_mm, angles[i % len(angles)], s.alternating,
                                    s.min_vector_mm)
        layers.append(L)
        if progress and (i % 10 == 0 or i == n - 1):
            progress(0.6 + 0.35 * (i + 1) / n)
    return layers


def slice_mesh(tris: np.ndarray, settings: SliceSettings, progress=None, cancel=None) -> list[Layer]:
    secs = cross_sections(tris, settings.layer_mm, progress, cancel)
    return build_layers(secs, settings, progress, cancel)
