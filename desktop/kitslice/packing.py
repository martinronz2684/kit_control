"""Intelligentes Auto-Anordnen (3D-Packen) für SLS – angelehnt an das 3D-Packing in Formlabs PreForm.

Grundlage ist ein echtes 3D-Belegungsraster (Voxel, Standard 2 mm) des idealen Druckbereichs:
  - jedes Teil wird in jeder erlaubten Lage (6 Seiten nach unten × 4 Drehungen um Z) gerastert;
    Säulen werden von der untersten bis zur obersten Fläche gefüllt (auf der sicheren Seite),
    Raum unter Überhängen und zwischen Teilen bleibt nutzbar
  - für alle Positionen zugleich wird per FFT-Korrelation geprüft, wo das Teil frei ist
    (Bauraum vorher um den Mindestabstand aufgeblasen – Abstand gilt in X, Y und Z)
  - gewählt wird die Lage mit der niedrigsten Oberkante, dann die tiefste, dann die mit dem meisten
    Kontakt zu Nachbarn und Wänden (dicht packen, volle Schichten)
  - mehrere Durchläufe mit verschiedenen Reihenfolgen im Zeitbudget; Sieger: geringste Bauhöhe, dann
    gleichmäßigste Schichtfläche (gleichmäßige Wärme)

SLS-Regeln (einstellbar): Mindestabstand zwischen Teilen, Abstand zum Rand des Bereichs, Abstand zur
Bauplatte (erste Schichten nur Pulver), gesperrte Teile bleiben liegen bzw. behalten ihre Lage.
"""
from __future__ import annotations

import math
import random
import time

import numpy as np

from kitslice.scene import IDEAL_XY, IDEAL_Z, Part, Scene, _samples

UPS = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 90), (0, 270)]
ZROT = [0, 90, 180, 270]


def volume(p: Part) -> float:
    t = p.transform(p.simple(6000))
    return abs(float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)


def _voxelize(tris: np.ndarray, res: float):
    """Teil -> Belegung (nx, ny, nz) samt Lage der Zelle (0,0,0) in mm. Säulen von unten bis oben gefüllt."""
    pts = _samples(tris, res * 0.6)
    lo = pts.min(axis=0)
    idx = np.floor((pts - lo) / res - 1e-6).clip(0).astype(int)
    n = idx.max(axis=0) + 1
    zmin = np.full((n[0], n[1]), n[2], dtype=int)
    zmax = np.full((n[0], n[1]), -1, dtype=int)
    np.minimum.at(zmin, (idx[:, 0], idx[:, 1]), idx[:, 2])
    np.maximum.at(zmax, (idx[:, 0], idx[:, 1]), idx[:, 2])
    k = np.arange(n[2])[None, None, :]
    vox = (k >= zmin[:, :, None]) & (k <= zmax[:, :, None])
    return vox, lo


def _dilate3(a: np.ndarray, g: int) -> np.ndarray:
    """Quader-Dilatation um g Zellen in allen Richtungen (Mindestabstand)."""
    out = a.copy()
    for ax in range(3):
        cur = out.copy()
        for s in range(1, g + 1):
            dst, src = [slice(None)] * 3, [slice(None)] * 3
            dst[ax], src[ax] = slice(s, None), slice(None, -s)
            cur[tuple(dst)] |= out[tuple(src)]
            dst[ax], src[ax] = slice(None, -s), slice(s, None)
            cur[tuple(dst)] |= out[tuple(src)]
        out = cur
    return out


class _Ctx:
    def __init__(self, area, height, gap, wall, floor, res):
        self.res = res
        inner = area - 2 * wall
        self.nx = self.ny = max(1, int(math.floor(inner / res)))
        self.nz = max(1, int(math.floor((height - floor) / res)))
        self.origin = np.array([-inner / 2, -inner / 2, floor])
        self.g = max(0, int(math.ceil(gap / res)))
        self.shape = (self.nx, self.ny, self.nz)
        self.cache = {}

    def shape_of(self, p: Part, rot):
        key = (id(p.mesh), tuple(rot), tuple(p.scale))
        if key not in self.cache:
            vox, lo = _voxelize(p.transform(p.simple(6000), rot), self.res)
            if any(v > s for v, s in zip(vox.shape, self.shape)):
                self.cache[key] = None
            else:
                F = np.conj(np.fft.rfftn(vox.astype(np.float32), s=self.shape))
                self.cache[key] = (vox, lo, F)
        return self.cache[key]


def _orientations(p: Part, allow: bool, ctx: _Ctx):
    if not allow or getattr(p, "lock_orient", False):
        return [(p.rot_x, p.rot_y, p.rot_z)]
    seen, out = set(), []
    for rx, ry in UPS:
        for rz in ZROT:
            sh = ctx.shape_of(p, (rx, ry, rz))
            if sh is None:
                continue
            sig = (sh[0].shape, hash(np.packbits(sh[0]).tobytes()))
            if sig not in seen:                  # symmetrische Lagen nur einmal prüfen
                seen.add(sig)
                out.append((rx, ry, rz))
    return out


def _best(ctx: _Ctx, occF, shell, shape, cur_top):
    """Beste freie Position einer Form: (Score, i, j, k) oder None."""
    vox = shape[0]
    sx, sy, sz = vox.shape
    corr = np.fft.irfftn(occF * shape[2], s=ctx.shape)
    free = corr[: ctx.nx - sx + 1, : ctx.ny - sy + 1, : ctx.nz - sz + 1] < 0.5
    if not free.any():
        return None
    ii, jj, kk = np.nonzero(free)
    top = kk + sz
    total = np.maximum(top, cur_top)
    order = np.lexsort((ii + jj, kk, top, total))[:300]
    best = None
    first = (int(total[order[0]]), int(top[order[0]]))
    for c in order:
        if (int(total[c]), int(top[c])) != first:
            break
        i, j, k = int(ii[c]), int(jj[c]), int(kk[c])
        score = (first[0], first[1], k, -shell(i, j, k, sx, sy, sz), i + j)
        if best is None or score < best[0]:
            best = (score, i, j, k)
    return best


def _shell_fn(occ_d):
    pad = np.pad(occ_d, 1, constant_values=True)     # Wände zählen als Nachbarn

    def shell(i, j, k, sx, sy, sz):
        return int(pad[i:i + sx + 2, j:j + sy + 2, k:k + sz + 2].sum())
    return shell


def _run(ctx: _Ctx, occ0: np.ndarray, order, allow_rot, cancel):
    occ = occ0.copy()
    cur_top = int(np.nonzero(occ.any(axis=(0, 1)))[0].max() + 1) if occ.any() else 0
    plan = []
    for p in order:
        if cancel and cancel():
            return None
        occ_d = _dilate3(occ, ctx.g)
        occF = np.fft.rfftn(occ_d.astype(np.float32))
        shell = _shell_fn(occ_d)
        best = None
        for rot in _orientations(p, allow_rot, ctx):
            sh = ctx.shape_of(p, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, cur_top)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], sh)
        if best is None:
            return None
        _, rot, i, j, k, sh = best
        vox = sh[0]
        occ[i:i + vox.shape[0], j:j + vox.shape[1], k:k + vox.shape[2]] |= vox
        cur_top = max(cur_top, k + vox.shape[2])
        plan.append((p, rot, i, j, k, sh))
    return cur_top, occ, plan


def _fixed_occ(ctx: _Ctx, parts) -> np.ndarray:
    occ = np.zeros(ctx.shape, dtype=bool)
    for q in parts:
        vox, lo = _voxelize(q.light(6000), ctx.res)
        o = np.floor((lo - ctx.origin) / ctx.res).astype(int)
        a0 = np.maximum(o, 0)
        a1 = np.minimum(o + np.array(vox.shape), ctx.shape)
        if (a1 <= a0).any():
            continue
        occ[a0[0]:a1[0], a0[1]:a1[1], a0[2]:a1[2]] |= vox[a0[0] - o[0]:a1[0] - o[0],
                                                          a0[1] - o[1]:a1[1] - o[1],
                                                          a0[2] - o[2]:a1[2] - o[2]]
    return occ


def _apply(ctx: _Ctx, plan):
    for p, rot, i, j, k, sh in plan:
        p.rot_x, p.rot_y, p.rot_z = rot
        p._cache = None
        pos = ctx.origin + np.array([i, j, k]) * ctx.res - sh[1]
        p.x, p.y, p.z_lift = float(pos[0]), float(pos[1]), float(pos[2])


def _layer_spread(occ: np.ndarray) -> float:
    """Wie ungleichmäßig die belegte Fläche über die Höhe verteilt ist (kleiner = gleichmäßigere Wärme)."""
    a = occ.sum(axis=(0, 1)).astype(float)
    nz = np.nonzero(a)[0]
    if not len(nz):
        return 0.0
    a = a[: nz.max() + 1]
    return float(a.std() / max(a.mean(), 1e-9))


def auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None, floor: float = 0.0) -> dict:
    """Packt die Teile (oder nur `only`) in den idealen Bereich. Liefert Kennzahlen."""
    if not scene.parts:
        return {"ok": True, "height": 0.0, "density": 0.0, "passes": 0}
    movers = [p for p in (only if only is not None else scene.parts) if not getattr(p, "lock_pos", False)]
    fixed = [p for p in scene.parts if p not in movers]
    if not movers:
        return {"ok": True, "height": 0.0, "density": 0.0, "passes": 0}
    ctx = _Ctx(area, height, gap, wall, floor, res)
    occ0 = _fixed_occ(ctx, fixed)
    vols = {id(p): volume(p) for p in movers}

    def dims(p):
        return sorted(p.size(), reverse=True)
    orders = [
        sorted(movers, key=lambda p: -vols[id(p)]),
        sorted(movers, key=lambda p: -float(np.prod(p.size()))),
        sorted(movers, key=lambda p: -dims(p)[0]),
        sorted(movers, key=lambda p: -dims(p)[0] * dims(p)[1]),
    ]
    rng = random.Random(7)
    t0 = time.time()
    best = None
    tried = k = 0
    while True:
        if k and time.time() - t0 > time_budget:
            break
        if k < len(orders):
            order = orders[k]
        else:
            if time.time() - t0 > time_budget or len(movers) < 3:
                break
            order = list(orders[k % len(orders)])
            for _ in range(max(1, len(order) // 4)):
                a = rng.randrange(len(order))
                b = min(len(order) - 1, a + rng.randint(1, 3))
                order[a], order[b] = order[b], order[a]
        k += 1
        r = _run(ctx, occ0, order, allow_rotation, cancel)
        if cancel and cancel():
            break
        tried += 1
        if r:
            top, occ, plan = r
            key = (top, round(_layer_spread(occ), 2))
            if best is None or key < best[0]:
                best = (key, plan)
        if progress:
            progress(min(0.99, max(k / (len(orders) + 1), (time.time() - t0) / max(time_budget, 0.1))))
        if len(movers) <= 1:
            break
        if k >= len(orders) and time.time() - t0 > time_budget:
            break
    if best is None:
        return {"ok": False, "height": 0.0, "density": 0.0, "passes": tried,
                "error": "Teile passen nicht in den idealen Bereich – Abstand verringern oder Teile verkleinern"}
    _apply(ctx, best[1])
    if not fixed:                                # Anordnung mittig (gleichmäßigste Temperatur)
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
         progress=None, cancel=None, floor: float = 0.0) -> int:
    """„Bauraum auffüllen“: Kopien von `part` hinzufügen, solange sie im Bereich Platz finden."""
    ctx = _Ctx(area, height, gap, wall, floor, res)
    occ = _fixed_occ(ctx, scene.parts)
    orients = _orientations(part, allow_rotation, ctx)
    added = 0
    while added < limit:
        if cancel and cancel():
            break
        occ_d = _dilate3(occ, ctx.g)
        occF = np.fft.rfftn(occ_d.astype(np.float32))
        shell = _shell_fn(occ_d)
        best = None
        for rot in orients:
            sh = ctx.shape_of(part, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, ctx.nz)      # Gesamthöhe zählt beim Auffüllen nicht
            if r and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], sh)
        if best is None:
            break
        _, rot, i, j, k, sh = best
        vox = sh[0]
        occ[i:i + vox.shape[0], j:j + vox.shape[1], k:k + vox.shape[2]] |= vox
        q = Part(f"{part.name} ({added + 2})", part.mesh, scale=part.scale)
        q.lock_orient = getattr(part, "lock_orient", False)
        _apply(ctx, [(q, rot, i, j, k, sh)])
        scene.add(q)
        added += 1
        if progress:
            progress(min(0.99, added / 60))
    return added
