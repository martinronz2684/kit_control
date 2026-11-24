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
    contour_first: bool = True

    @property
    def empty(self) -> bool:
        return not len(self.contours) and not len(self.hatches)


def layer_count(tris: np.ndarray, layer_mm: float) -> int:
    return max(1, int(math.ceil(float(tris[:, :, 2].max()) / layer_mm - 1e-9)))


def cross_sections(tris, layer_mm: float, progress=None, cancel=None, rng=None, mesh=None):
    """Schnitte in der Mitte jeder Schicht: z = (i + 0.5) * Schichtdicke, i = 0 .. n-1.
    Liefert eine Liste von Querschnitten (Liste von Polygonen, noch nicht ausgerichtet).
    rng = (von, bis): nur diese Schichten (für das Rechnen auf mehreren Kernen).
    mesh = (Eckpunkte, Dreiecke): bereits indiziertes Netz (tris wird dann nicht gebraucht)."""
    verts, faces = mesh if mesh is not None else index_mesh(tris)
    vz = verts[:, 2]
    if vz.min() < -1e-6:
        raise ValueError("Bauteil liegt unter der Bauplatte")
    n = max(1, int(math.ceil(vz.max() / layer_mm - 1e-9)))
    lo_i, hi_i = rng if rng else (0, n)
    hi_i = min(hi_i, n)
    fz = vz[faces]
    fmin, fmax = fz.min(axis=1), fz.max(axis=1)
    out = []
    BLOCK = 24
    for b0 in range(lo_i, hi_i, BLOCK):
        b1 = min(hi_i, b0 + BLOCK)
        zlo, zhi = (b0 + 0.5) * layer_mm, (b1 - 0.5) * layer_mm
        sub = np.flatnonzero((fmin <= zhi) & (fmax > zlo))      # nur Dreiecke, die diesen Block schneiden
        smin, smax = fmin[sub], fmax[sub]
        for i in range(b0, b1):
            if cancel and cancel():
                raise SliceCancelled()
            z = (i + 0.5) * layer_mm
            act = sub[(smin <= z) & (smax > z)]
            out.append(_section(verts, faces[act], z) if len(act) else [])
            if progress and (i % 10 == 0 or i == n - 1):
                progress(0.6 * (i + 1 - lo_i) / max(1, hi_i - lo_i))
    return out


def _section(verts, faces, z):
    above = verts[faces, 2] >= z                                  # (m, 3); Punkte auf der Ebene zählen als oben
    edges = []
    pts = {}
    for a, b in ((0, 1), (1, 2), (2, 0)):
        cross = above[:, a] != above[:, b]
        va, vb = faces[:, a].astype(np.int64), faces[:, b].astype(np.int64)   # int64: Schlüssel laufen sonst über
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
    # Erweiterungen (Standard = Verhalten von Central)
    contour_first: bool = True               # Kontur vor Füllung (Central); False = Füllung zuerst
    hatch_angle_step_deg: float | None = None  # z. B. 67: Winkel wächst je Schicht um diesen Wert
    island_mm: float = 0.0                   # > 0: Schachbrettschraffur mit Feldern dieser Größe
    skin_layers: int = 0                     # > 0: so viele Schichten unter/über Flächen gelten als Haut
    core_every: int = 1                      # im Kern nur jede n-te Schraffurlinie (Abstand x n)
    shrink_pct: tuple = (0.0, 0.0, 0.0)      # Schwundausgleich X/Y/Z in %
    optimize_path: bool = False              # Inseln und Konturen nach kürzestem Weg sortieren
    keep_thin: bool = True                   # dünne Wände nicht verlieren (Kontur mit kleinerem Versatz)

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
            contour_first=bool(p.get("contour_first", True)),
            hatch_angle_step_deg=p.get("hatch_angle_step_deg"),
            island_mm=float(p.get("island_mm") or 0.0),
            skin_layers=int(p.get("skin_layers") or 0),
            core_every=max(1, int(round((p.get("core_spacing_um") or p["hatch_spacing_um"]) / p["hatch_spacing_um"]))),
            shrink_pct=tuple(float((p.get("shrink_pct") or {}).get(a, 0.0)) for a in "xyz"),
            optimize_path=bool(p.get("optimize_path", False)),
            keep_thin=bool(p.get("keep_thin", True)),
        )


def _angle(s: SliceSettings, i: int, angles: list) -> float:
    if s.hatch_angle_step_deg:
        return angles[0] + math.radians(float(s.hatch_angle_step_deg)) * i
    return angles[i % len(angles)]


def _nearest_order(items, start, key_start, key_end):
    """Gierige Reihenfolge nach kürzestem Sprung (für Konturen und Inseln)."""
    rest = list(items)
    out = []
    pos = start
    while rest:
        j = min(range(len(rest)), key=lambda t: (key_start(rest[t])[0] - pos[0]) ** 2 + (key_start(rest[t])[1] - pos[1]) ** 2)
        it = rest.pop(j)
        out.append(it)
        pos = key_end(it)
    return out


def build_layers(sections, s: SliceSettings, progress=None, cancel=None, base: int = 0,
                 n_total: int | None = None, only=None) -> list[Layer]:
    """sections[j] gehört zur Schicht base + j. only = (von, bis) relativ zu sections: nur diese ausgeben."""
    layers = []
    n = len(sections)
    n_total = n_total if n_total is not None else base + n
    angles = [math.radians(a) for a in s.hatch_angles_deg] or [0.0]
    prepared = {}            # Schicht -> ausgerichtete Polygone
    rasters = {}             # Schicht -> Raster des Füllbereichs (nur für Haut/Kern)

    def loops_of(i):
        if i not in prepared:
            sec = sections[i] if 0 <= i < n else []
            lp = [G.simplify(l, s.min_vector_mm) for l in sec]
            prepared[i] = G.orient([l for l in lp if len(l) >= 3]) if lp else []
        return prepared[i]

    def raster_of(i):
        if i not in rasters:
            rasters[i] = G.Raster(G.offset(loops_of(i), s.hatch_offset_mm)) if 0 <= i < n and loops_of(i) else None
        return rasters[i]

    o0, o1 = only if only else (0, n)
    for i in range(o0, o1):
        if cancel and cancel():
            raise SliceCancelled()
        for old in [k for k in prepared if k < i - s.skin_layers - 1]:
            prepared.pop(old, None)
            rasters.pop(old, None)
        z = (base + i + 0.5) * s.layer_mm
        L = Layer(z)
        loops = loops_of(i)
        if loops:
            contours = []
            if s.draw_original_boundary:
                contours += loops
            cur = loops
            for pi in range(s.perimeters):              # Perimeter nacheinander, außen zuerst
                cur = G.offset(cur, s.perimeter_offset_mm, keep_thin=(pi == 0 and s.keep_thin))
                contours += cur
            infill = G.offset(loops, s.hatch_offset_mm)  # Füllversatz vom Originalrand
            ang = _angle(s, base + i, angles)
            core = None
            if s.skin_layers > 0 and s.core_every > 1:
                rs = [raster_of(j) for j in range(i - s.skin_layers, i + s.skin_layers + 1)]
                if all(r is not None for r in rs):
                    comb = G.Raster([], res=rs[0].res, half=rs[0].half)
                    comb.mask = np.logical_and.reduce([r.mask for r in rs])
                    core = comb.contains
            kw = dict(alternating=s.alternating, min_len=s.min_vector_mm, core=core, core_every=s.core_every)
            regions = G.groups(infill) if s.optimize_path else [infill]
            hatch_parts = []
            for reg in regions:
                if s.island_mm > 0:
                    h = G.hatch_islands(reg, s.hatch_spacing_mm, ang, s.island_mm, **kw)
                else:
                    h = G.hatch(reg, s.hatch_spacing_mm, ang, **kw)
                if len(h):
                    hatch_parts.append(np.asarray(h, dtype=float).reshape(-1, 4))
            if s.optimize_path:
                contours = _nearest_order(contours, (0.0, 0.0), lambda c: c[0], lambda c: c[0])
                last = contours[-1][0] if contours and s.contour_first else (0.0, 0.0)
                hatch_parts = _nearest_order(hatch_parts, last, lambda h: h[0][:2], lambda h: h[-1][2:])
            L.contours = contours
            L.hatches = np.concatenate(hatch_parts) if hatch_parts else np.zeros((0, 4))
            L.contour_first = s.contour_first
        layers.append(L)
        if progress and (i % 10 == 0 or i == o1 - 1):
            progress(0.6 + 0.35 * (i + 1 - o0) / max(1, o1 - o0))
    return layers


_W = {}


def _share(arr):
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(create=True, size=max(1, arr.nbytes))
    np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)[...] = arr
    return shm, (shm.name, arr.shape, arr.dtype.str)


def _attach(desc):
    from multiprocessing import shared_memory
    name, shape, dt = desc
    shm = shared_memory.SharedMemory(name=name)
    return shm, np.ndarray(shape, dtype=np.dtype(dt), buffer=shm.buf)


def _winit(vdesc, fdesc, settings, n):
    sv, verts = _attach(vdesc)
    sf, faces = _attach(fdesc)
    _W.update(shm=(sv, sf), mesh=(verts, faces), s=settings, n=n)


def _wrun(a, b):
    s = _W["s"]
    n = _W["n"]
    lo, hi = max(0, a - s.skin_layers), min(n, b + s.skin_layers)
    secs = cross_sections(None, s.layer_mm, rng=(lo, hi), mesh=_W["mesh"])
    layers = build_layers(secs, s, base=lo, n_total=n, only=(a - lo, b - lo))
    return a, [([np.asarray(c) for c in L.contours], np.asarray(L.hatches), L.contour_first, L.z) for L in layers]


def workers() -> int:
    import os
    return max(1, min(16, (os.cpu_count() or 1) - 1))


def slice_mesh(tris, settings: SliceSettings, progress=None, cancel=None, parallel=None, mesh=None) -> list[Layer]:
    """tris: Dreiecksuppe (n, 3, 3) oder None mit mesh = (Eckpunkte, Dreiecke)."""
    if mesh is None:
        mesh = index_mesh(tris)
    verts, faces = mesh
    if any(settings.shrink_pct):                 # Schwundausgleich: um die Plattenmitte bzw. ab z = 0 skalieren
        verts = verts * (1.0 + np.asarray(settings.shrink_pct) / 100.0)
    n = max(1, int(math.ceil(float(verts[:, 2].max()) / settings.layer_mm - 1e-9)))
    nw = workers() if parallel is None else parallel
    if nw > 1 and n >= 120 and len(faces) * n > 2_000_000:
        try:
            return _slice_parallel(verts, faces, settings, n, nw, progress, cancel)
        except SliceCancelled:
            raise
        except Exception:                        # z. B. Prozesse nicht startbar – dann eben auf einem Kern
            pass
    secs = cross_sections(None, settings.layer_mm, progress, cancel, mesh=(verts, faces))
    return build_layers(secs, settings, progress, cancel)


def _slice_parallel(verts, faces, settings, n, nw, progress, cancel):
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    chunk = max(10, n // (nw * 4))
    jobs = [(a, min(n, a + chunk)) for a in range(0, n, chunk)]
    out = [None] * n
    done_layers = 0
    sv, vdesc = _share(np.ascontiguousarray(verts))
    sf, fdesc = _share(np.ascontiguousarray(faces))
    try:
        with ProcessPoolExecutor(max_workers=nw, initializer=_winit, initargs=(vdesc, fdesc, settings, n)) as ex:
            pending = {ex.submit(_wrun, a, b) for a, b in jobs}
            while pending:
                if cancel and cancel():
                    for f in pending:
                        f.cancel()
                    raise SliceCancelled()
                fin, pending = wait(pending, timeout=0.3, return_when=FIRST_COMPLETED)
                for f in fin:
                    a, res = f.result()
                    for k, (cont, hat, cf, z) in enumerate(res):
                        L = Layer(z, list(cont), hat)
                        L.contour_first = cf
                        out[a + k] = L
                        done_layers += 1
                if progress:
                    progress(0.95 * done_layers / n)
    finally:
        for shm in (sv, sf):
            shm.close()
            shm.unlink()
    return out
