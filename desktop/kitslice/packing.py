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

from kitslice.scene import mesh_uid

from kitslice.scene import IDEAL_XY, IDEAL_Z, Part, Scene, _samples

UPS = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 90), (0, 270)]
ZROT = [0, 90, 180, 270]


def volume(p: Part) -> float:
    t = p.transform(p.simple(6000))
    return abs(float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)


# ---------------------------------------------------------------- SLS-Ausrichtungsregeln
TILT = 10.0          # Grad: große flache Teile leicht kippen (gegen Verzug / Curling)


_QCACHE: dict = {}


def quality(p: Part, rot) -> dict:
    """Bewertet eine Lage nach SLS-Ausrichtungsregeln (kleiner = besser, 0 = ideal).
      flat   große ebene Flächen waagerecht (Verzug/Curling)
      jump   Querschnittssprünge von Schicht zu Schicht (thermische Spannung)
      stair  flach ansteigende Flächen (Treppenstufen)
      round  liegende Rundungen/Bohrungen (oval, Treppen) statt stehend
      down   nach unten zeigende Flächen (rauer)
      tall   Bauhöhe des Teils (Zeit, Wärme)
    """
    key = (mesh_uid(p.mesh), tuple(rot), tuple(p.scale))
    if key in _QCACHE:
        return _QCACHE[key]
    _QCACHE[key] = r = _quality(p, rot)
    return r


def _quality(p: Part, rot) -> dict:
    t = p.transform(p.simple(6000), rot)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.linalg.norm(n, axis=1)
    ok = a > 1e-12
    t, n, a = t[ok], n[ok] / a[ok, None], a[ok] / 2
    if not len(a):
        return {"score": 0.0}
    A = float(a.sum())
    nz = n[:, 2]
    # größte waagerechte Fläche auf einer Höhe (Platten, große Böden)
    hor = np.abs(nz) > 0.985
    flat = 0.0
    if hor.any():
        zc = np.round(t[hor, :, 2].mean(axis=1) / 0.5).astype(int)
        u, inv = np.unique(zc, return_inverse=True)
        flat = float(np.bincount(inv, a[hor]).max())
    # flache Steigungen: 5°–40° zur Waagerechten -> sichtbare Treppen
    stair = float(a[(np.abs(nz) > 0.77) & (np.abs(nz) <= 0.985)].sum())
    # Rundungen: gekrümmte Flächen (Normale nicht achsparallel). Liegend = Normale hat z-Anteil.
    curved = (np.abs(n) < 0.97).all(axis=1) | ((np.abs(nz) > 0.05) & (np.abs(nz) < 0.95))
    lying = curved & (np.abs(nz) > 0.2) & (np.abs(nz) < 0.98)
    rnd = float(a[lying].sum())
    down = float(a[nz < -0.3].sum())
    h = float(t[:, :, 2].max() - t[:, :, 2].min())
    # Querschnitt je 1-mm-Schicht aus dem Volumen-Raster
    vox, _ = _voxelize(t, 1.0)
    lay = vox.sum(axis=(0, 1)).astype(float)
    jump = float(np.abs(np.diff(lay)).max() / max(lay.max(), 1.0)) if len(lay) > 1 else 0.0
    d = max(A, 1.0)
    sc = (3.0 * max(0.0, flat - 150.0) / d + 1.5 * jump + 1.0 * stair / d + 1.0 * rnd / d
          + 0.3 * down / d + 0.004 * h)
    return {"score": float(sc), "flat": flat, "jump": jump, "stair": stair / d, "round": rnd / d,
            "down": down / d, "height": h}


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
        if gap >= 1.0:                           # Raster so wählen, dass der Abstand genau aufgeht
            res = min(res, max(1.0, gap / max(1, round(gap / res))))
        self.res = res
        inner = area - 2 * wall
        self.nx = self.ny = max(1, int(math.floor(inner / res)))
        self.nz = max(1, int(math.floor((height - floor) / res)))
        self.origin = np.array([-inner / 2, -inner / 2, floor])
        self.g = max(0, int(math.ceil(gap / res)))
        self.shape = (self.nx, self.ny, self.nz)
        self.cache = {}

    def shape_of(self, p: Part, rot):
        key = (mesh_uid(p.mesh), tuple(rot), tuple(p.scale))
        if key not in self.cache:
            vox, lo = _voxelize(p.transform(p.simple(6000), rot), self.res)
            if any(v > s for v, s in zip(vox.shape, self.shape)):
                self.cache[key] = None
            else:
                F = np.conj(np.fft.rfftn(vox.astype(np.float32), s=self.shape))
                self.cache[key] = (vox, lo, F)
        return self.cache[key]


def _orientations(p: Part, allow: bool, ctx: _Ctx, quality_w: float = 0.5):
    """Erlaubte Lagen. quality_w 0 = nur Packdichte, 1 = nur die besten Lagen nach SLS-Regeln."""
    if not allow or getattr(p, "lock_orient", False):
        return [(p.rot_x, p.rot_y, p.rot_z)]
    key = ("orients", mesh_uid(p.mesh), tuple(p.scale), round(quality_w, 2))
    if key in ctx.cache:
        return ctx.cache[key]
    seen, cand = set(), []
    for rx, ry in UPS:
        for rz in ZROT:
            sh = ctx.shape_of(p, (rx, ry, rz))
            if sh is None:
                continue
            sig = (sh[0].shape, hash(np.packbits(sh[0]).tobytes()))
            if sig not in seen:                  # symmetrische Lagen nur einmal prüfen
                seen.add(sig)
                cand.append((rx, ry, rz))
    if quality_w >= 0.99 and cand:
        q = {r: quality(p, r)["score"] for r in cand}
        best = min(q.values())
        # große flache Teile: zusätzlich leicht gekippte Varianten der besten Lagen
        for r in sorted(cand, key=q.get)[:2]:
            if quality(p, r).get("flat", 0) > 400:
                for tr in ((r[0] + TILT, r[1], r[2]), (r[0], r[1] + TILT, r[2]),
                           (r[0] + TILT, r[1] + TILT, r[2])):
                    if ctx.shape_of(p, tr) is not None:
                        q[tr] = quality(p, tr)["score"]
                        cand.append(tr)
        best = min(q.values())
        span = max(max(q.values()) - best, 1e-9)
        tol = span * (1.0 - quality_w) ** 2 + 1e-9      # 1.0 -> nur die beste, 0.5 -> beste Viertel
        cand = sorted([r for r in cand if q[r] <= best + tol], key=q.get)
    ctx.cache[key] = cand
    return cand


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


def _run(ctx: _Ctx, occ0: np.ndarray, order, allow_rot, cancel, quality_w=0.5):
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
        for rot in _orientations(p, allow_rot, ctx, quality_w):
            sh = ctx.shape_of(p, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, cur_top)
            if r:
                # gleiche Bauhöhe: die Lage nach SLS-Regeln bevorzugen (Ausrichtung kostet nie Höhe)
                qs = 0.0
                key = (r[0][0], r[0][1], qs) + tuple(r[0][2:])
                if best is None or key < best[0]:
                    best = (key, rot, r[1], r[2], r[3], sh)
        if best is None:
            return None
        _, rot, i, j, k, sh = best
        vox = sh[0]
        occ[i:i + vox.shape[0], j:j + vox.shape[1], k:k + vox.shape[2]] |= vox
        cur_top = max(cur_top, k + vox.shape[2])
        plan.append((p, rot, i, j, k, sh))
    return cur_top, occ, plan


def _compact(ctx: _Ctx, occ0: np.ndarray, plan):
    """Schwerkraft: jedes Teil so weit nach unten setzen wie frei ist (keine vermeidbaren Leerschichten)."""
    plan = list(plan)
    for _ in range(4):
        moved = False
        occ = occ0.copy()
        for p, rot, i, j, k, sh in plan:
            v = sh[0]
            occ[i:i + v.shape[0], j:j + v.shape[1], k:k + v.shape[2]] |= v
        for n in sorted(range(len(plan)), key=lambda m: plan[m][4]):
            p, rot, i, j, k, sh = plan[n]
            v = sh[0]
            sx, sy, sz = v.shape
            others = occ.copy()
            others[i:i + sx, j:j + sy, k:k + sz] &= ~v
            # Nachbarn im Teil-Fenster aufblasen (Mindestabstand), dann tiefste freie Höhe suchen
            g = ctx.g
            a0, a1 = max(0, i - g), min(ctx.nx, i + sx + g)
            b0, b1 = max(0, j - g), min(ctx.ny, j + sy + g)
            win = _dilate3(others[a0:a1, b0:b1, :], g)[i - a0:i - a0 + sx, j - b0:j - b0 + sy, :]
            new_k = k
            for kk in range(0, k):
                if not (win[:, :, kk:kk + sz] & v).any():
                    new_k = kk
                    break
            if new_k != k:
                occ = others
                occ[i:i + sx, j:j + sy, new_k:new_k + sz] |= v
                plan[n] = (p, rot, i, j, new_k, sh)
                moved = True
        if not moved:
            break
    occ = occ0.copy()
    for p, rot, i, j, k, sh in plan:
        v = sh[0]
        occ[i:i + v.shape[0], j:j + v.shape[1], k:k + v.shape[2]] |= v
    top = int(np.nonzero(occ.any(axis=(0, 1)))[0].max() + 1) if occ.any() else 0
    return top, occ, plan


def _colmap(p: Part, h: float):
    """Säulenkarte eines Teils im Weltraster (Zellgröße h): unterste/oberste Fläche je Zelle, exakt in mm
    (relativ zu z_lift), aus dem vollen Netz."""
    t = p.transform(p.mesh) + np.array([p.x, p.y, 0.0])
    pts = _samples(t, h * 0.7)
    ij = np.floor(pts[:, :2] / h).astype(np.int64)
    o = ij.min(axis=0)
    ij -= o
    n = ij.max(axis=0) + 1
    bot = np.full(n, np.inf)
    top = np.full(n, -np.inf)
    np.minimum.at(bot, (ij[:, 0], ij[:, 1]), pts[:, 2])
    np.maximum.at(top, (ij[:, 0], ij[:, 1]), pts[:, 2])
    return o, bot, top


def _kernel(gap: float, h: float):
    """Versätze (dx, dy) mit seitlichem Abstand < gap und dem dort nötigen senkrechten Abstand."""
    r = int(math.ceil(gap / h))
    out = []
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            L = h * math.hypot(dx, dy)
            if L < gap:
                out.append((dx, dy, math.sqrt(max(0.0, gap * gap - L * L))))
    return r, out


def _clearance_map(o, bot, top, gap, h):
    """Säulenkarte um den Mindestabstand aufgeblasen: je Zelle tiefste Unterseite − Abstand und höchste
    Oberseite + Abstand aller Teilpunkte in Reichweite (seitlich und schräg exakt)."""
    r, ker = _kernel(gap, h)
    n = np.array(bot.shape) + 2 * r
    B = np.full(n, np.inf)
    T = np.full(n, -np.inf)
    for dx, dy, vg in ker:
        sl = (slice(r + dx, r + dx + bot.shape[0]), slice(r + dy, r + dy + bot.shape[1]))
        np.minimum(B[sl], bot - vg, out=B[sl])
        np.maximum(T[sl], top + vg, out=T[sl])
    return o - r, B, T


def settle(scene: Scene, movers, gap: float, h: float = 0.5, floor: float = 0.0, passes: int = 6) -> float:
    """Exaktes Absenken: jedes Teil so weit nach unten, bis es den Mindestabstand zu einem Teil darunter
    (seitlich und schräg exakt) oder die Bauplatte erreicht. Liefert die gesamte Absenkung in mm."""
    if not movers:
        return 0.0
    maps = {id(q): _colmap(q, h) for q in scene.parts}
    clear = {id(q): _clearance_map(*maps[id(q)], gap, h) for q in scene.parts}
    mover_ids = {id(q) for q in movers}
    total = 0.0
    for _ in range(passes):
        moved = 0.0
        for p in sorted(scene.parts, key=lambda q: q.z_lift):
            if id(p) not in mover_ids:
                continue
            o, bot, top = maps[id(p)]
            pdef = np.isfinite(bot)
            pb, pt = bot + p.z_lift, top + p.z_lift
            d = float(pb[pdef].min() - floor)
            for q in scene.parts:
                if q is p or d <= 0.05:
                    continue
                qo, QB, QT = clear[id(q)]
                a0 = np.maximum(o, qo)
                a1 = np.minimum(o + np.array(bot.shape), qo + np.array(QB.shape))
                if (a1 <= a0).any():
                    continue
                ps = (slice(a0[0] - o[0], a1[0] - o[0]), slice(a0[1] - o[1], a1[1] - o[1]))
                qs = (slice(a0[0] - qo[0], a1[0] - qo[0]), slice(a0[1] - qo[1], a1[1] - qo[1]))
                m = pdef[ps] & np.isfinite(QB[qs])
                if not m.any():
                    continue
                b, t = pb[ps][m], pt[ps][m]
                qb, qt = QB[qs][m] + q.z_lift, QT[qs][m] + q.z_lift
                below = qt <= b + 1e-6
                above = qb >= t - 1e-6
                if (~below & ~above).any():
                    d = 0.0                          # seitlich schon an der Grenze
                    break
                if below.any():
                    d = min(d, float((b[below] - qt[below]).min()))
            if d > 0.05:
                p.z_lift = float(p.z_lift - d)
                moved += d
        total += moved
        if moved < 0.05:
            break
    return total


def empty_height(parts, step: float = 0.1) -> float:
    """Exakt gemessene Höhe ohne jedes Bauteil (Schichten, in denen der Laser nichts zu tun hätte)."""
    iv = []
    for p in parts:
        t = p.light(6000)
        iv.append(np.stack([t[:, :, 2].min(axis=1), t[:, :, 2].max(axis=1)], axis=1))
    if not iv:
        return 0.0
    iv = np.concatenate(iv)
    top = float(iv[:, 1].max())
    n = int(math.ceil(top / step))
    diff = np.zeros(n + 2, int)
    a = np.clip(np.floor(iv[:, 0] / step).astype(int), 0, n)
    b = np.clip(np.ceil(iv[:, 1] / step).astype(int), 0, n)
    np.add.at(diff, a, 1)
    np.add.at(diff, b + 1, -1)
    cov = np.cumsum(diff)[:n] > 0
    return float((~cov).sum() * step)


def _empty_layers(occ: np.ndarray) -> int:
    a = occ.any(axis=(0, 1))
    nz = np.nonzero(a)[0]
    return int((~a[: nz.max() + 1]).sum()) if len(nz) else 0


def _stamp(ctx, occ0, plan, skip=-1):
    occ = occ0.copy()
    for n, (p, rot, i, j, k, sh) in enumerate(plan):
        if n != skip:
            v = sh[0]
            occ[i:i + v.shape[0], j:j + v.shape[1], k:k + v.shape[2]] |= v
    return occ


def _top_of(plan, skip=-1):
    return max([k + sh[0].shape[2] for n, (p, rot, i, j, k, sh) in enumerate(plan) if n != skip] or [0])


def _improve(ctx: _Ctx, occ0, plan, allow_rot, quality_w, deadline, cancel=None):
    """Nachverdichten: das jeweils höchste Teil herausnehmen und an der tiefsten freien Stelle (alle Lagen)
    neu einsetzen, solange die Bauhöhe sinkt oder oben weniger Teile liegen. Füllt Lücken unter
    Überhängen und an Rändern, die beim ersten Einsortieren frei geblieben sind."""
    plan = list(plan)
    tried = set()
    while time.time() < deadline and not (cancel and cancel()):
        tops = [k + sh[0].shape[2] for (p, rot, i, j, k, sh) in plan]
        order = sorted(range(len(plan)), key=lambda n: -tops[n])
        cand = [n for n in order if (n, plan[n][2:5]) not in tried]
        if not cand:
            break
        n = cand[0]
        tried.add((n, plan[n][2:5]))
        p, rot0, i0, j0, k0, sh0 = plan[n]
        occ = _stamp(ctx, occ0, plan, skip=n)
        occ_d = _dilate3(occ, ctx.g)
        occF = np.fft.rfftn(occ_d.astype(np.float32))
        shell = _shell_fn(occ_d)
        rest_top = _top_of(plan, skip=n)
        best = None
        for rot in _orientations(p, allow_rot, ctx, quality_w):
            sh = ctx.shape_of(p, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, rest_top)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], sh)
        if best is None:
            continue
        old_total = max(rest_top, tops[n])
        new_top = best[4] + best[5][0].shape[2]
        if (max(rest_top, new_top), new_top) < (old_total, tops[n]):
            plan[n] = (p, best[1], best[2], best[3], best[4], best[5])
            tried.clear()
    return plan


def _reorient(ctx: _Ctx, occ0, plan, deadline, cancel=None):
    """„Ausgewogen“: nach dem dichten Packen jedem Teil eine bessere Lage nach SLS-Regeln geben, wo das
    ohne jede zusätzliche Bauhöhe geht (Bauhöhe hat Vorrang)."""
    plan = list(plan)
    total = _top_of(plan)
    order = sorted(range(len(plan)), key=lambda n: -quality(plan[n][0], plan[n][1])["score"])
    for n in order:
        if time.time() > deadline or (cancel and cancel()):
            break
        p, rot0 = plan[n][0], plan[n][1]
        q0 = quality(p, rot0)["score"]
        better = [r for r in _orientations(p, True, ctx, 0.0) if quality(p, r)["score"] < q0 - 0.05]
        if not better or getattr(p, "lock_orient", False):
            continue
        occ = _stamp(ctx, occ0, plan, skip=n)
        occ_d = _dilate3(occ, ctx.g)
        occF = np.fft.rfftn(occ_d.astype(np.float32))
        shell = _shell_fn(occ_d)
        best = None
        for r in sorted(better, key=lambda r: quality(p, r)["score"]):
            sh = ctx.shape_of(p, r)
            if sh is None:
                continue
            b = _best(ctx, occF, shell, sh, total)
            old_top = plan[n][4] + plan[n][5][0].shape[2]
            if b and b[0][0] <= total and b[0][1] <= old_top:       # nicht höher als vorher -> keine Lücken
                best = (r, b[1], b[2], b[3], sh)
                break                                   # beste Lage, die ohne Mehrhöhe passt
        if best:
            plan[n] = (p,) + best
    return plan


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


def _state(parts):
    return [(p, p.rot_x, p.rot_y, p.rot_z, p.x, p.y, p.z_lift) for p in parts]


def _restore(st):
    for p, rx, ry, rz, x, y, z in st:
        p.rot_x, p.rot_y, p.rot_z, p.x, p.y, p.z_lift = rx, ry, rz, x, y, z
        p._cache = None


def auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None, floor: float = 0.0,
              quality_w: float = 0.5) -> dict:
    """„Ausgewogen“ (0 < quality_w < 1): Lagen nach SLS-Regeln nur nehmen, wenn sie die Bauhöhe kaum erhöhen
    (höchstens 15 %), sonst die dichteste Anordnung. Bauhöhe hat Vorrang."""
    if not (0 < quality_w < 0.99) or not allow_rotation:
        return _auto_pack(scene, gap, wall, allow_rotation, only, area, height, res, time_budget,
                          progress, cancel, floor, quality_w)
    return _auto_pack(scene, gap, wall, allow_rotation, only, area, height, res, time_budget,
                      progress, cancel, floor, 0.0, reorient=True)


def _auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None, floor: float = 0.0,
              quality_w: float = 0.5, reorient: bool = False) -> dict:
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
        if k and time.time() - t0 > 0.6 * time_budget:
            break
        if k < len(orders):
            order = orders[k]
        else:
            if time.time() - t0 > 0.6 * time_budget or len(movers) < 3:
                break
            order = list(orders[k % len(orders)])
            for _ in range(max(1, len(order) // 4)):
                a = rng.randrange(len(order))
                b = min(len(order) - 1, a + rng.randint(1, 3))
                order[a], order[b] = order[b], order[a]
        k += 1
        r = _run(ctx, occ0, order, allow_rotation, cancel, quality_w)
        if cancel and cancel():
            break
        tried += 1
        if r is None and quality_w > 0 and best is None and k >= 2:
            break                                    # mit den besten Lagen passt es nicht
        if r:
            top, occ, plan = _compact(ctx, occ0, r[2])
            key = (top, round(_layer_spread(occ), 2))
            if best is None or key < best[0]:
                best = (key, plan, _empty_layers(occ) * ctx.res)
        if progress:
            progress(min(0.99, max(k / (len(orders) + 1), (time.time() - t0) / max(time_budget, 0.1))))
        if len(movers) <= 1:
            break
        if k >= len(orders) and time.time() - t0 > 0.6 * time_budget:
            break
    if best is None and quality_w > 0 and not (cancel and cancel()):
        # mit den besten Lagen passt es nicht -> alle Lagen erlauben
        r = _auto_pack(scene, gap, wall, allow_rotation, only, area, height, res, time_budget / 2,
                      progress, cancel, floor, 0.0)
        r["relaxed"] = True
        return r
    if best is None:
        return {"ok": False, "height": 0.0, "density": 0.0, "passes": tried,
                "error": "Teile passen nicht in den idealen Bereich – Abstand verringern oder Teile verkleinern"}
    if len(movers) > 1:
        plan = _improve(ctx, occ0, best[1], allow_rotation, quality_w, max(t0 + time_budget, time.time() + 0.3), cancel)
        top, occ, plan = _compact(ctx, occ0, plan)
        if reorient:
            plan = _reorient(ctx, occ0, plan, time.time() + max(1.0, 0.3 * time_budget), cancel)
            top, occ, plan = _compact(ctx, occ0, plan)
        best = ((top, 0), plan, _empty_layers(occ) * ctx.res)
    _apply(ctx, best[1])
    settle(scene, movers, gap, floor=floor)
    empty = best[2]
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
            "density": round(float(dens) * 100, 1), "passes": tried,
            "empty_mm": round(empty_height(scene.parts), 1)}


def fill(scene: Scene, part: Part, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
         area: float = IDEAL_XY, height: float = IDEAL_Z, res: float = 2.0, limit: int = 300,
         progress=None, cancel=None, floor: float = 0.0, quality_w: float = 0.5) -> int:
    """„Bauraum auffüllen“: das Teil selbst neu setzen und Kopien hinzufügen, solange Platz ist.
    Andere Teile bleiben liegen. Nach jeder Runde exakt absenken und die frei gewordene Höhe nachfüllen."""
    ctx = _Ctx(area, height, gap, wall, floor, res)
    reuse = not getattr(part, "lock_pos", False)          # Original wird zur ersten „Kopie“
    orients = _orientations(part, allow_rotation, ctx, quality_w)
    added = 0
    placed = []
    for _round in range(4):
        occ = _fixed_occ(ctx, [q for q in scene.parts if not (reuse and q is part and not placed)])
        new = 0
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
            if reuse and not placed:
                q = part
            else:
                q = Part(f"{part.name} ({added + 2})", part.mesh, scale=part.scale)
                q.lock_orient = getattr(part, "lock_orient", False)
                scene.add(q)
                added += 1
            _apply(ctx, [(q, rot, i, j, k, sh)])
            placed.append(q)
            new += 1
            if progress:
                progress(min(0.99, len(placed) / 60))
        if placed:
            settle(scene, placed, gap, floor=floor)
        if not new or (cancel and cancel()):
            break
    return added
