"""Intelligentes Auto-Anordnen (3D-Packen) für SLS – angelehnt an das 3D-Packing in Formlabs PreForm.

Grundlage ist ein echtes 3D-Belegungsraster (Voxel, Standard 2 mm) des idealen Druckbereichs:
  - jedes Teil wird in jeder erlaubten Lage (6 Seiten nach unten × 4 Drehungen um Z) mit seiner echten
    Form gerastert: Becher-Innenräume, Aussparungen und Raum unter Überhängen bleiben frei, kleine Teile
    dürfen dort hinein (Verschachteln)
  - für alle Positionen zugleich wird per FFT-Korrelation geprüft, wo das Teil frei ist
    (Bauraum vorher um den Mindestabstand aufgeblasen – Abstand gilt in X, Y und Z)
  - verhakungsfrei: erlaubt sind nur Positionen, die von oben auf einem freien Weg erreichbar sind
    (Flutfüllung im Raum der freien Positionen, wie bei Cui et al. 2023). In umgekehrter Reihenfolge lässt
    sich so jedes Teil aus dem Pulverkuchen ziehen – keine Kettenglieder, nichts eingeschlossen
  - gewählt wird die Lage mit der niedrigsten Oberkante, dann die, die leere Schichten mit abdeckt, dann
    die tiefste, dann die mit dem meisten Kontakt zu Nachbarn und Wänden (dicht packen, volle Schichten)
  - mehrere Durchläufe mit verschiedenen Reihenfolgen im Zeitbudget; Sieger: geringste Bauhöhe, dann
    wenigste leere Schichten (jede kostet Beschichten + Aufwärmen ohne Nutzen), dann gleichmäßigste
    Schichtfläche (gleichmäßige Wärme, kein Curling durch Flächensprünge)

SLS-Regeln (einstellbar): Mindestabstand zwischen Teilen, Abstand zum Rand des Bereichs, Abstand zur
Bauplatte (erste Schichten nur Pulver), gesperrte Teile bleiben liegen bzw. behalten ihre Lage.
"""
from __future__ import annotations

import math
import random
import time

import numpy as np

from kitslice.scene import mesh_uid

from kitslice import scene as _sc
from kitslice.scene import Part, Scene, _samples

UPS = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 90), (0, 270)]
ZROT = [0, 90, 180, 270]


def volume(p: Part) -> float:
    t = p.transform(p.simple(6000))
    return abs(float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)


# ---------------------------------------------------------------- SLS-Ausrichtungsregeln
TILT = 10.0          # Grad: große flache Teile leicht kippen (gegen Verzug / Curling)


_QCACHE: dict = {}
_VOXCACHE: dict = {}


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
    """Teil -> Belegung (nx, ny, nz) samt Lage der Zelle (0,0,0) in mm. Echte Form (Hohlräume bleiben frei),
    auf der sicheren Seite gerastert (jede Zelle mit Material ist belegt)."""
    lo = tris.reshape(-1, 3).min(axis=0)
    t = tris - lo
    f = 1                                                   # ein Strahl je Zelle, Oberflächenpunkte feiner
    k, z0, z1 = _sc.dexels(t, res / f, merge=res / f)
    ix = (k // _sc.KX - _sc._K0).clip(0) // f
    iy = (k % _sc.KX - _sc._K0).clip(0) // f            # (Zelle −1 = Punkt genau auf x = 0 → Zelle 0)
    k0 = np.floor(z0 / res - 1e-6).clip(0).astype(int)
    k1 = np.floor(z1 / res - 1e-6).clip(0).astype(int)
    n = np.array([ix.max() + 1, iy.max() + 1, k1.max() + 1])
    d = np.zeros((n[0], n[1], n[2] + 1), np.int32)
    np.add.at(d, (ix, iy, k0), 1)
    np.add.at(d, (ix, iy, k1 + 1), -1)
    return np.cumsum(d, axis=2)[:, :, : n[2]] > 0, lo


def _reachable(free: np.ndarray) -> np.ndarray:
    """Freie Positionen, die von oben (oberste Ebene) über freie Nachbarpositionen erreichbar sind.
    Senkrecht wird je Säule der ganze zusammenhängende freie Abschnitt auf einmal gefüllt, seitlich
    Schritt für Schritt – so reichen meist wenige Runden."""
    if not free.any():
        return free
    nx, ny, nz = free.shape
    st = free.copy()
    st[:, :, 1:] &= ~free[:, :, :-1]                        # Beginn eines freien Abschnitts in der Säule
    run = np.cumsum(st.ravel()).reshape(free.shape) * free   # Abschnitts-Nummer (global eindeutig, 0 = belegt)
    seed = np.zeros(int(run.max()) + 1, bool)
    seed[run[:, :, -1][free[:, :, -1]]] = True
    seed[0] = False
    reach = seed[run]
    for _ in range(4 * (nx + ny)):
        g = reach.copy()
        g[1:] |= reach[:-1]; g[:-1] |= reach[1:]
        g[:, 1:] |= reach[:, :-1]; g[:, :-1] |= reach[:, 1:]
        new = run[g & free & ~reach]
        if not len(new):
            break
        seed[new] = True
        reach = seed[run]
    return reach


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
            vk = key + (round(self.res, 4),)
            if vk not in _VOXCACHE:                       # Rasterung bleibt über mehrere Anordnen-Läufe erhalten
                if len(_VOXCACHE) > 4000:
                    _VOXCACHE.clear()
                _VOXCACHE[vk] = _voxelize(p.transform(p.simple(6000), rot), self.res)
            vox, lo = _VOXCACHE[vk]
            if any(v > s for v, s in zip(vox.shape, self.shape)):
                self.cache[key] = None
            else:
                F = np.conj(np.fft.rfftn(vox.astype(np.float32), s=self.shape, axes=(0, 1, 2)))
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


def _free(ctx: _Ctx, occF, shape):
    """Freie und von oben erreichbare Positionen einer Form (verhakungsfrei)."""
    sx, sy, sz = shape[0].shape
    corr = np.fft.irfftn(occF * shape[2], s=ctx.shape, axes=(0, 1, 2))
    return _reachable(corr[: ctx.nx - sx + 1, : ctx.ny - sy + 1, : ctx.nz - sz + 1] < 0.5)


def _best(ctx: _Ctx, occF, shell, shape, cur_top, empty=None):
    """Beste freie Position einer Form: (Score, i, j, k) oder None.
    empty: Präfixsumme der leeren Schichten unterhalb der aktuellen Oberkante (abdecken bevorzugt)."""
    sx, sy, sz = shape[0].shape
    free = _free(ctx, occF, shape)
    if not free.any():
        return None
    ii, jj, kk = np.nonzero(free)
    top = kk + sz
    total = np.maximum(top, cur_top)
    if empty is not None and empty[-1] > 0:
        cover = empty[np.minimum(top, len(empty) - 1)] - empty[np.minimum(kk, len(empty) - 1)]
    else:
        cover = np.zeros(len(kk), int)
    order = np.lexsort((ii + jj, kk, -cover, top, total))[:300]
    best = None
    first = (int(total[order[0]]), int(top[order[0]]), -int(cover[order[0]]))
    for c in order:
        if (int(total[c]), int(top[c]), -int(cover[c])) != first:
            break
        i, j, k = int(ii[c]), int(jj[c]), int(kk[c])
        score = first + (k, -shell(i, j, k, sx, sy, sz), i + j)
        if best is None or score < best[0]:
            best = (score, i, j, k)
    return best


def _empty_prefix(occ: np.ndarray, cur_top: int):
    e = ~occ[:, :, :cur_top].any(axis=(0, 1))
    return np.concatenate([[0], np.cumsum(e)])


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
        empty = _empty_prefix(occ, cur_top)
        best = None
        for rot in _orientations(p, allow_rot, ctx, quality_w):
            sh = ctx.shape_of(p, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, cur_top, empty)
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


def _compact(ctx: _Ctx, occ0: np.ndarray, plan):
    """Schwerkraft: jedes Teil so weit nach unten setzen wie frei ist (keine vermeidbaren Leerschichten)."""
    plan = list(plan)
    for _ in range(4):
        moved = False
        order_moved = []
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
                # verhakungsfrei bleiben: neue Lage muss mit allen anderen Teilen von oben erreichbar sein
                fr = _free(ctx, np.fft.rfftn(_dilate3(others, g).astype(np.float32)), sh)
                if not fr[i, j, new_k]:
                    ks = [kk for kk in range(new_k, k) if fr[i, j, kk]]
                    new_k = ks[0] if ks else k
            if new_k != k:
                occ = others
                occ[i:i + sx, j:j + sy, new_k:new_k + sz] |= v
                plan[n] = (p, rot, i, j, new_k, sh)
                order_moved.append(n)
                moved = True
        if order_moved:                              # zuletzt eingesetzt = zuerst herausgenommen
            mv = set(order_moved)
            plan = [e for m, e in enumerate(plan) if m not in mv] + [plan[m] for m in order_moved]
        if not moved:
            break
    occ = occ0.copy()
    for p, rot, i, j, k, sh in plan:
        v = sh[0]
        occ[i:i + v.shape[0], j:j + v.shape[1], k:k + v.shape[2]] |= v
    top = int(np.nonzero(occ.any(axis=(0, 1)))[0].max() + 1) if occ.any() else 0
    return top, occ, plan


def _kernel(gap: float, h: float):
    """Versätze (dx, dy) mit seitlichem Abstand < gap und dem dort nötigen senkrechten Abstand."""
    r = int(math.ceil(gap / h))
    out = []
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            L = h * max(0.0, math.hypot(dx, dy) - 1.0)          # Zellen sind h breit: auf der sicheren Seite
            if L < gap:
                out.append((dx, dy, math.sqrt(max(0.0, gap * gap - L * L))))
    return r, out


def _grow(D, gap, h):
    """Echte Form um den Mindestabstand aufgeblasen (seitlich und schräg)."""
    _, ker = _kernel(gap, h)
    k, z0, z1 = D
    ks = [k + dx * _sc.KX + dy for dx, dy, _ in ker]
    a = np.concatenate([z0 - vg for _, _, vg in ker])
    b = np.concatenate([z1 + vg for _, _, vg in ker])
    return _sc._merge_rows(np.concatenate(ks), a, b)


def settle(scene: Scene, movers, gap: float, h: float = 0.5, floor: float = 0.0, passes: int = 6) -> float:
    """Exaktes Absenken mit der echten Teilform: jedes Teil so weit nach unten, bis es den Mindestabstand zu
    einem Teil darunter oder die Bauplatte erreicht (auch in Becher und unter Überhänge hinein).
    Liefert die gesamte Absenkung in mm."""
    if not movers:
        return 0.0
    base = {id(q): _sc.part_dexels(q, h) for q in scene.parts}
    base = {i: (k, z0 - q.z_lift, z1 - q.z_lift) for q in scene.parts for i, (k, z0, z1) in [(id(q), base[id(q)])]}
    grown = {}
    mover_ids = {id(q) for q in movers}
    boxes = {}
    total = 0.0
    for _ in range(passes):
        moved = 0.0
        for p in sorted(scene.parts, key=lambda q: q.z_lift):
            if id(p) not in mover_ids:
                continue
            k, z0, z1 = base[id(p)]
            b, t = z0 + p.z_lift, z1 + p.z_lift
            d = float(b.min() - floor)
            lo, hi = p.bbox()
            for q in scene.parts:
                if q is p or d <= 0.05:
                    continue
                qlo, qhi = q.bbox()
                if any(lo[m] > qhi[m] + gap or qlo[m] > hi[m] + gap for m in (0, 1)) or qlo[2] > hi[2] + gap:
                    continue
                if id(q) not in grown:
                    grown[id(q)] = _grow(base[id(q)], gap, h)
                G = grown[id(q)]
                ai, bi = _sc._pairs((k, b, t), G)
                if not len(ai):
                    continue
                qb, qt = G[1][bi] + q.z_lift, G[2][bi] + q.z_lift
                pb, pt = b[ai], t[ai]
                below = qt <= pb + 1e-6
                above = qb >= pt - 1e-6
                if (~below & ~above).any():
                    d = 0.0                          # schon an der Grenze
                    break
                if below.any():
                    d = min(d, float((pb[below] - qt[below]).min()))
            if d > 0.05:
                p.z_lift = float(p.z_lift - d)
                moved += d
        total += moved
        if moved < 0.05:
            break
    return total


def empty_bands(parts, step: float = 0.1) -> list:
    """Höhenbereiche [a, b) ohne jedes Bauteil zwischen Bauplatte und Oberkante (Laser hätte nichts zu tun)."""
    iv = []
    for p in parts:
        t = p.light(6000)
        iv.append(np.stack([t[:, :, 2].min(axis=1), t[:, :, 2].max(axis=1)], axis=1))
    if not iv:
        return []
    iv = np.concatenate(iv)
    top = float(iv[:, 1].max())
    n = int(math.ceil(top / step))
    diff = np.zeros(n + 2, int)
    a = np.clip(np.floor(iv[:, 0] / step).astype(int), 0, n)
    b = np.clip(np.ceil(iv[:, 1] / step).astype(int), 0, n)
    np.add.at(diff, a, 1)
    np.add.at(diff, b + 1, -1)
    cov = np.cumsum(diff)[:n] > 0
    out, i = [], 0
    while i < n:
        if not cov[i]:
            j = i
            while j < n and not cov[j]:
                j += 1
            out.append((i * step, j * step))
            i = j
        else:
            i += 1
    return out


def empty_height(parts, step: float = 0.1) -> float:
    """Exakt gemessene Höhe ohne jedes Bauteil (Schichten, in denen der Laser nichts zu tun hätte)."""
    return float(sum(b - a for a, b in empty_bands(parts, step)))


def _room_up(scene: Scene, p, gap: float, h: float = 0.5, grown=None) -> float:
    """Wie weit ein Teil angehoben werden kann, ohne den Mindestabstand zu einem Teil darüber zu verletzen."""
    k, z0, z1 = _sc.part_dexels(p, h)
    lo, hi = p.bbox()
    room = float(_sc.IDEAL_Z - hi[2])
    for q in scene.parts:
        if q is p:
            continue
        qlo, qhi = q.bbox()
        if any(lo[m] > qhi[m] + gap or qlo[m] > hi[m] + gap for m in (0, 1)) or qhi[2] < lo[2] - gap:
            continue
        key = (id(q), q.x, q.y, q.z_lift, q.rot_x, q.rot_y, q.rot_z)
        if grown is None or key not in grown:
            G = _grow(_sc.part_dexels(q, h), gap, h)
            if grown is not None:
                grown[key] = G
        else:
            G = grown[key]
        ai, bi = _sc._pairs((k, z0, z1), G)
        if not len(ai):
            continue
        qb, qt, pb, pt = G[1][bi], G[2][bi], z0[ai], z1[ai]
        above = qb >= pt - 1e-6
        below = qt <= pb + 1e-6
        if (~above & ~below).any():
            return 0.0
        if above.any():
            room = min(room, float((qb[above] - pt[above]).min()))
    return max(0.0, room)


def cover_bands(scene: Scene, movers, gap: float, rounds: int = 8) -> int:
    """Leere Höhenbereiche schließen: ein Teil darunter, das nach oben Luft hat, so weit anheben, dass es den
    Bereich überbrückt – ohne die Bauhöhe zu erhöhen und ohne unten eine neue Lücke zu öffnen.
    (Jede leere Schicht kostet Beschichten + Aufwärmen ohne Nutzen.) Liefert die Zahl der Anhebungen."""
    done = 0
    grown = {}
    mover_ids = {id(q) for q in movers}
    for _ in range(rounds):
        bands = [bd for bd in empty_bands(scene.parts) if bd[0] > 0.05]
        if not bands:
            break
        top = max(q.bbox()[1][2] for q in scene.parts)
        before = empty_height(scene.parts)
        a, b = bands[0]
        best = None
        for p in scene.parts:
            if id(p) not in mover_ids:
                continue
            lo, hi = p.bbox()
            need = b - hi[2] + 0.15
            if hi[2] > a + 1e-6 or need <= 0 or lo[2] + need > a - 0.05 or hi[2] + need > top:
                continue
            if _room_up(scene, p, gap, grown=grown) < need:
                continue
            p.z_lift += need
            after = empty_height(scene.parts)
            p.z_lift -= need
            if after < before - 0.05 and (best is None or (after, need) < best[0]):
                best = ((after, need), p)
        if best is None:
            break
        best[1].z_lift += best[0][1]
        done += 1
    return done


def _empty_layers(occ: np.ndarray) -> int:
    a = occ.any(axis=(0, 1))
    nz = np.nonzero(a)[0]
    return int((~a[: nz.max() + 1]).sum()) if len(nz) else 0


def _stamp(ctx, occ0, plan, skip=-1):
    occ = occ0.copy()
    for n, e in enumerate(plan):
        if e is None:
            continue
        p, rot, i, j, k, sh = e
        if n != skip:
            v = sh[0]
            occ[i:i + v.shape[0], j:j + v.shape[1], k:k + v.shape[2]] |= v
    return occ


def _top_of(plan, skip=-1):
    return max([e[4] + e[5][0].shape[2] for n, e in enumerate(plan) if e is not None and n != skip] or [0])


def _improve(ctx: _Ctx, occ0, plan, allow_rot, quality_w, deadline, cancel=None):
    """Nachverdichten: das jeweils höchste Teil herausnehmen und an der tiefsten freien Stelle (alle Lagen)
    neu einsetzen, solange die Bauhöhe sinkt oder oben weniger Teile liegen. Füllt Lücken unter
    Überhängen und an Rändern, die beim ersten Einsortieren frei geblieben sind."""
    plan = list(plan)
    tried = set()
    while time.time() < deadline and not (cancel and cancel()):
        tops = [k + sh[0].shape[2] for (p, rot, i, j, k, sh) in plan]
        order = sorted(range(len(plan)), key=lambda n: -tops[n])
        cand = [n for n in order if (id(plan[n][0]), plan[n][2:5]) not in tried]
        if not cand:
            break
        n = cand[0]
        tried.add((id(plan[n][0]), plan[n][2:5]))
        p, rot0, i0, j0, k0, sh0 = plan[n]
        occ = _stamp(ctx, occ0, plan, skip=n)
        occ_d = _dilate3(occ, ctx.g)
        occF = np.fft.rfftn(occ_d.astype(np.float32))
        shell = _shell_fn(occ_d)
        rest_top = _top_of(plan, skip=n)
        empty = _empty_prefix(occ, rest_top)
        best = None
        for rot in _orientations(p, allow_rot, ctx, quality_w):
            sh = ctx.shape_of(p, rot)
            if sh is None:
                continue
            r = _best(ctx, occF, shell, sh, rest_top, empty)
            if r and (best is None or r[0] < best[0]):
                best = (r[0], rot, r[1], r[2], r[3], sh)
        if best is None:
            continue
        old_total = max(rest_top, tops[n])
        new_top = best[4] + best[5][0].shape[2]
        e_old = _empty_layers(_stamp(ctx, occ0, plan))
        cand = plan[:n] + plan[n + 1:] + [(p, best[1], best[2], best[3], best[4], best[5])]
        e_new = _empty_layers(_stamp(ctx, occ0, cand))
        if (max(rest_top, new_top), e_new, new_top) < (old_total, e_old, tops[n]):
            plan = cand                                  # ans Ende: verhakungsfrei geprüft gegen alle anderen
            tried.clear()
    return plan


def _reorient(ctx: _Ctx, occ0, plan, deadline, cancel=None):
    """„Ausgewogen“: nach dem dichten Packen jedem Teil eine bessere Lage nach SLS-Regeln geben, wo das
    ohne jede zusätzliche Bauhöhe geht (Bauhöhe hat Vorrang)."""
    plan = list(plan)
    total = _top_of(plan)
    order = sorted(range(len(plan)), key=lambda n: -quality(plan[n][0], plan[n][1])["score"])
    for n in order:
        if plan[n] is None:
            continue
        if time.time() > deadline or (cancel and cancel()):
            break
        p, rot0 = plan[n][0], plan[n][1]
        q0 = quality(p, rot0)["score"]
        better = [r for r in _orientations(p, True, ctx, 0.0) if quality(p, r)["score"] < q0 - 0.05]
        if not better or getattr(p, "lock_orient", False):
            continue
        live = [e if m != n else None for m, e in enumerate(plan)]
        occ = _stamp(ctx, occ0, [e for e in live if e is not None])
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
            plan[n] = None
            plan.append((p,) + best)                    # ans Ende: verhakungsfrei gegen alle anderen geprüft
    return [e for e in plan if e is not None]


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


def _score_state(scene: Scene, area: float, height: float):
    """(Bauhöhe, leere Höhe) einer gültigen Anordnung – None, wenn Teile überlappen oder herausragen."""
    if not scene.parts or scene.collision_pairs():
        return None
    h = area / 2
    for p in scene.parts:
        lo, hi = p.bbox()
        if lo[0] < -h - 1e-6 or lo[1] < -h - 1e-6 or hi[0] > h + 1e-6 or hi[1] > h + 1e-6 or hi[2] > height + 1e-6:
            return None
    return (round(max(p.bbox()[1][2] for p in scene.parts), 1), round(empty_height(scene.parts), 1))


def _state(parts):
    return [(p, p.rot_x, p.rot_y, p.rot_z, p.x, p.y, p.z_lift) for p in parts]


def _restore(st):
    for p, rx, ry, rz, x, y, z in st:
        p.rot_x, p.rot_y, p.rot_z, p.x, p.y, p.z_lift = rx, ry, rz, x, y, z
        p._cache = None


def auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float | None = None, height: float | None = None, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None, floor: float = 0.0,
              quality_w: float = 0.5) -> dict:
    """„Ausgewogen“ (0 < quality_w < 1): Lagen nach SLS-Regeln nur nehmen, wenn sie die Bauhöhe kaum erhöhen
    (höchstens 15 %), sonst die dichteste Anordnung. Bauhöhe hat Vorrang."""
    area = _sc.IDEAL_XY if area is None else area
    height = _sc.IDEAL_Z if height is None else height
    if not (0 < quality_w < 0.99) or not allow_rotation:
        return _auto_pack(scene, gap, wall, allow_rotation, only, area, height, res, time_budget,
                          progress, cancel, floor, quality_w)
    return _auto_pack(scene, gap, wall, allow_rotation, only, area, height, res, time_budget,
                      progress, cancel, floor, 0.0, reorient=True)


def _auto_pack(scene: Scene, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
              only=None, area: float | None = None, height: float | None = None, res: float = 2.0,
              time_budget: float = 8.0, progress=None, cancel=None, floor: float = 0.0,
              quality_w: float = 0.5, reorient: bool = False) -> dict:
    """Packt die Teile (oder nur `only`) in den idealen Bereich. Liefert Kennzahlen."""
    area = _sc.IDEAL_XY if area is None else area
    height = _sc.IDEAL_Z if height is None else height
    if not scene.parts:
        return {"ok": True, "height": 0.0, "density": 0.0, "passes": 0}
    movers = [p for p in (only if only is not None else scene.parts) if not getattr(p, "lock_pos", False)]
    fixed = [p for p in scene.parts if p not in movers]
    if not movers:
        return {"ok": True, "height": 0.0, "density": 0.0, "passes": 0}
    ctx = _Ctx(area, height, gap, wall, floor, res)
    occ0 = _fixed_occ(ctx, fixed)
    vols = {id(p): volume(p) for p in movers}
    # bisherige Anordnung als Kandidat: Anordnen darf nie schlechter werden als das, was schon da liegt
    st0 = _state(scene.parts)
    prev = _score_state(scene, area, height) if only is None else None

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
            key = (top, _empty_layers(occ), round(_layer_spread(occ), 2))
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
    if best is None and cancel and cancel():
        return {"ok": False, "height": 0.0, "density": 0.0, "passes": tried,
                "error": "Anordnen abgebrochen – Anordnung unverändert"}
    if best is None:
        return {"ok": False, "height": 0.0, "density": 0.0, "passes": tried,
                "error": "Teile passen nicht in den idealen Bereich – Abstand verringern oder Teile verkleinern"}
    if len(movers) > 1:
        plan = _improve(ctx, occ0, best[1], allow_rotation, quality_w, max(t0 + time_budget, time.time() + 0.3), cancel)
        top, occ, plan = _compact(ctx, occ0, plan)
        if reorient:
            plan = _reorient(ctx, occ0, plan, time.time() + max(1.0, 0.3 * time_budget), cancel)
            top, occ, plan = _compact(ctx, occ0, plan)
        best = ((top, 0, 0), plan, _empty_layers(occ) * ctx.res)
    _apply(ctx, best[1])
    settle(scene, movers, gap, floor=floor)
    cover_bands(scene, movers, gap)
    kept = False
    if prev is not None:
        new_st, new_sc = _state(scene.parts), _score_state(scene, area, height)
        _restore(st0)                                # bisherige Lage nur nachverdichten (absenken, Lücken schließen)
        settle(scene, movers, gap, floor=floor)
        cover_bands(scene, movers, gap)
        old_sc = _score_state(scene, area, height)
        if old_sc is not None and (new_sc is None or old_sc < new_sc):
            kept = True                              # bisherige (nachverdichtete) Anordnung ist besser
        else:
            _restore(new_st)
    empty = best[2]
    if not fixed and not kept:                   # Anordnung mittig (gleichmäßigste Temperatur)
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
            "density": round(float(dens) * 100, 1), "passes": tried, "kept": kept,
            "empty_mm": round(empty_height(scene.parts), 1)}


def fill(scene: Scene, part: Part, gap: float = 3.0, wall: float = 2.0, allow_rotation: bool = True,
         area: float | None = None, height: float | None = None, res: float = 2.0, limit: int = 300,
         progress=None, cancel=None, floor: float = 0.0, quality_w: float = 0.5) -> int:
    """„Bauraum auffüllen“: das Teil selbst neu setzen und Kopien hinzufügen, solange Platz ist.
    Andere Teile bleiben liegen. Nach jeder Runde exakt absenken und die frei gewordene Höhe nachfüllen."""
    area = _sc.IDEAL_XY if area is None else area
    height = _sc.IDEAL_Z if height is None else height
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
            cover_bands(scene, placed, gap)
        if not new or (cancel and cancel()):
            break
    return added
