"""Intelligentes Auto-Anordnen (3D-Packen) – angelehnt an das 3D-Packing in Formlabs PreForm.

Ziel wie bei SLS üblich: möglichst niedrige Bauhöhe bei hoher Packdichte (weniger Pulver, kürzerer Druck).

  - jedes Teil darf in 24 achsparallelen Lagen liegen (6 Seiten nach unten × 4 Drehungen um Z),
    gesperrte Teile behalten Lage („Ausrichtung sperren“) bzw. Position („Position sperren“)
  - Platzierung über Höhenkarten: jedes Teil fällt von oben auf die schon gepackten Teile,
    mit Mindestabstand zwischen Teilen und zum Rand des Bereichs
  - mehrere Durchläufe mit verschiedenen Reihenfolgen (Volumen, Höhe, Grundfläche, Zufall) innerhalb
    eines Zeitbudgets; genommen wird der Durchlauf mit der geringsten Bauhöhe
  - „Auffüllen“: ein Teil so oft kopieren, wie es in den Bereich passt
"""
from __future__ import annotations

import math
import random
import time

import numpy as np

from kitslice.scene import IDEAL_XY, IDEAL_Z, Part, Scene, _dilate, _profile

# (rot_x, rot_y) für die 6 Seiten nach unten
UPS = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 90), (0, 270)]
ZROT = [0, 90, 180, 270]


def volume(p: Part) -> float:
    t = p._oriented()
    return abs(float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)


class _Ctx:
    def __init__(self, area, height, gap, wall, res):
        self.res = res
        self.inner = area - 2 * wall
        self.n = max(1, int(math.floor(self.inner / res)))
        self.origin = -self.inner / 2
        self.gap = gap
        self.g = max(0, int(math.ceil(gap / res)))
        self.height = height
        self.profiles = {}

    def profile(self, p: Part, rot):
        key = (id(p), rot, tuple(p.scale))
        if key not in self.profiles:
            old = (p.rot_x, p.rot_y, p.rot_z)
            p.rot_x, p.rot_y, p.rot_z = rot
            p._cache = None
            pr = _profile(p._oriented(), self.res)
            p.rot_x, p.rot_y, p.rot_z = old
            p._cache = None
            if pr is not None:
                bot, top, mx, my = pr
                occ = np.isfinite(bot)
                pr = (bot, top, mx, my, float(np.nanmax(top[occ])), np.nonzero(occ))
            self.profiles[key] = pr
        return self.profiles[key]


def _orientations(p: Part, allow: bool):
    if not allow or getattr(p, "lock_orient", False):
        return [(p.rot_x, p.rot_y, p.rot_z)]
    out, seen = [], set()
    for rx, ry in UPS:
        for rz in ZROT:
            p2 = (rx, ry, rz)
            if p2 not in seen:
                seen.add(p2)
                out.append(p2)
    return out


def _place(ctx: _Ctx, H: np.ndarray, prof, cur_max: float):
    """Beste Lage eines Profils in der Höhenkarte: (Score, i, j, z)."""
    bot, top, mx, my, h, (rows, cols) = prof
    ph, pw = bot.shape
    n = ctx.n
    if ph > n or pw > n:
        return None
    Hd = _dilate(H, ctx.g)
    L = np.full((n - ph + 1, n - pw + 1), -np.inf)
    # Zeilen/Spalten ausdünnen: Säulen eines Teils ändern sich selten von Zelle zu Zelle
    for r, c in zip(rows, cols):
        np.maximum(L, Hd[r:r + n - ph + 1, c:c + n - pw + 1] - bot[r, c], out=L)
    z = np.maximum(np.where(np.isfinite(L), L + ctx.gap, 0.0), 0.0)
    tops = z + h
    total = np.maximum(tops, cur_max)
    ii, jj = np.mgrid[0:n - ph + 1, 0:n - pw + 1]
    score = np.round(total, 2) * 1e9 + np.round(tops, 2) * 1e6 + ii * n + jj
    k = int(np.argmin(score))
    i, j = divmod(k, score.shape[1])
    return float(score.flat[k]), i, j, float(z[i, j])


def _stamp(H, prof, i, j, z):
    bot, top, *_ = prof
    occ = np.isfinite(top)
    sub = H[i:i + top.shape[0], j:j + top.shape[1]]
    sub[occ] = np.maximum(sub[occ], z + top[occ])


def _fixed_map(ctx: _Ctx, parts) -> np.ndarray:
    H = np.full((ctx.n, ctx.n), -np.inf)
    for q in parts:
        pr = _profile(q.placed(), ctx.res)
        if pr is None:
            continue
        _, top, mx, my = pr
        j0, i0 = int(round((mx - ctx.origin) / ctx.res)), int(round((my - ctx.origin) / ctx.res))
        for r in range(top.shape[0]):
            ii = i0 + r
            if not 0 <= ii < ctx.n:
                continue
            for c in range(top.shape[1]):
                jj = j0 + c
                if 0 <= jj < ctx.n and np.isfinite(top[r, c]):
                    H[ii, jj] = max(H[ii, jj], top[r, c])
    return H


def _run(ctx, H0, order, allow_rot, cancel):
    H = H0.copy()
    cur = float(np.max(H[np.isfinite(H)])) if np.isfinite(H).any() else 0.0
    plan = []
    for p in order:
        if cancel and cancel():
            return None
        best = None
        for rot in _orientations(p, allow_rot):
            prof = ctx.profile(p, rot)
            if prof is None:
                continue
            r = _place(ctx, H, prof, cur)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], prof)
        if best is None:
            return None
        _, rot, i, j, z, prof = best
        _stamp(H, prof, i, j, z)
        cur = max(cur, z + prof[4])
        plan.append((p, rot, i, j, z, prof))
    return cur, plan


def auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None) -> dict:
    """Packt die Teile (oder nur `only`) in den idealen Bereich. Liefert Kennzahlen."""
    if not scene.parts:
        return {"ok": True, "height": 0.0, "density": 0.0, "passes": 0}
    movers = [p for p in (only if only is not None else scene.parts) if not getattr(p, "lock_pos", False)]
    fixed = [p for p in scene.parts if p not in movers]
    ctx = _Ctx(area, height, gap, wall, res)
    H0 = _fixed_map(ctx, fixed)
    vols = {id(p): volume(p) for p in movers}

    def dims(p):
        return sorted(p.size(), reverse=True)
    orders = [
        sorted(movers, key=lambda p: -vols[id(p)]),
        sorted(movers, key=lambda p: -float(np.prod(p.size()))),
        sorted(movers, key=lambda p: -dims(p)[0]),
        sorted(movers, key=lambda p: -(p.size()[0] * p.size()[1])),
        sorted(movers, key=lambda p: -dims(p)[1] * dims(p)[2]),
    ]
    rng = random.Random(42)
    t0 = time.time()
    best = None
    tried = 0
    k = 0
    while True:
        if k < len(orders):
            order = orders[k]
        else:
            if time.time() - t0 > time_budget or len(movers) < 3:
                break
            order = list(orders[0])
            # leicht gestörte Reihenfolge: Nachbarn tauschen
            for _ in range(max(1, len(order) // 3)):
                a = rng.randrange(len(order))
                b = min(len(order) - 1, a + rng.randint(1, 3))
                order[a], order[b] = order[b], order[a]
        k += 1
        r = _run(ctx, H0, order, allow_rotation, cancel)
        if cancel and cancel():
            break
        tried += 1
        if r and (best is None or r[0] < best[0] - 1e-6):
            best = r
        if progress:
            progress(min(0.99, max(k / (len(orders) + 1), (time.time() - t0) / max(time_budget, 0.1))))
        if k >= len(orders) and time.time() - t0 > time_budget:
            break
        if len(movers) <= 1 and k >= 1:
            break
    if best is None:
        return {"ok": False, "height": 0.0, "density": 0.0, "passes": tried,
                "error": "Teile passen nicht in den Bereich – Abstand verringern oder Teile verkleinern"}
    hmax, plan = best
    for p, rot, i, j, z, prof in plan:
        p.rot_x, p.rot_y, p.rot_z = rot
        p._cache = None
        _, _, mx, my, *_ = prof
        p.x = ctx.origin + j * res - mx
        p.y = ctx.origin + i * res - my
        p.z_lift = z
    if not fixed:                                # ganze Anordnung in die Mitte (gleichmäßigste Temperatur)
        lo = np.min([q.bbox()[0] for q in scene.parts], axis=0)
        hi = np.max([q.bbox()[1] for q in scene.parts], axis=0)
        dx, dy = -(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2
        for q in scene.parts:
            q.x += dx
            q.y += dy
    total_h = float(max(p.bbox()[1][2] for p in scene.parts))
    vol = sum(volume(p) for p in scene.parts)
    dens = vol / (area * area * max(total_h, 1e-6))
    if progress:
        progress(1.0)
    return {"ok": bool(total_h <= height + 1e-6), "height": round(total_h, 1),
            "density": round(float(dens) * 100, 1), "passes": tried}


def fill(scene: Scene, part: Part, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
         area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0, limit: int = 300,
         progress=None, cancel=None) -> int:
    """„Bauraum auffüllen“: Kopien von `part` hinzufügen, solange sie im Bereich Platz finden."""
    ctx = _Ctx(area, height, gap, wall, res)
    H = _fixed_map(ctx, scene.parts)
    cur = float(np.max(H[np.isfinite(H)])) if np.isfinite(H).any() else 0.0
    added = 0
    while added < limit:
        if cancel and cancel():
            break
        q = Part(f"{part.name} ({added + 2})", part.mesh, rot_x=part.rot_x, rot_y=part.rot_y,
                 rot_z=part.rot_z, scale=part.scale)
        q.lock_orient = getattr(part, "lock_orient", False)
        best = None
        for rot in _orientations(q, allow_rotation):
            prof = ctx.profile(part, rot)        # Profile des Originals wiederverwenden
            if prof is None:
                continue
            r = _place(ctx, H, prof, max(cur, height))   # nur innerhalb der Höhe – Gesamthöhe zählt nicht
            if r and r[3] + prof[4] <= height + 1e-6 and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], prof)
        if best is None:
            break
        _, rot, i, j, z, prof = best
        _stamp(H, prof, i, j, z)
        cur = max(cur, z + prof[4])
        q.rot_x, q.rot_y, q.rot_z = rot
        _, _, mx, my, *_ = prof
        q.x = ctx.origin + j * res - mx
        q.y = ctx.origin + i * res - my
        q.z_lift = z
        scene.add(q)
        added += 1
        if progress:
            progress(min(0.99, added / 50))
    return added
