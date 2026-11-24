"""Ebene Geometrie eines Querschnitts: Ausrichtung, Versatz (Offset) und Schraffur.

Ein Querschnitt ist eine Liste geschlossener Polygone (np.ndarray (n, 2), erster Punkt nicht wiederholt).
Material liegt nach der Gerade-Ungerade-Regel innen. Nach orient() sind Außenränder gegen den
Uhrzeigersinn und Löcher im Uhrzeigersinn ausgerichtet – das Material liegt dann immer links.
"""
from __future__ import annotations

import math

import numpy as np


def _nx(a):
    """a[i+1] zyklisch (schneller als np.roll)."""
    return np.concatenate((a[1:], a[:1]))


def _pv(a):
    """a[i-1] zyklisch."""
    return np.concatenate((a[-1:], a[:-1]))


def area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]) + x[-1] * y[0] - x[0] * y[-1])


def perimeter(p: np.ndarray) -> float:
    e = _nx(p) - p
    return float(np.hypot(e[:, 0], e[:, 1]).sum())


def _inside(pt, poly: np.ndarray) -> bool:
    x, y = pt
    xs, ys = poly[:, 0], poly[:, 1]
    xe, ye = np.roll(xs, -1), np.roll(ys, -1)
    m = (ys > y) != (ye > y)
    if not m.any():
        return False
    xi = xs[m] + (y - ys[m]) * (xe[m] - xs[m]) / (ye[m] - ys[m])
    return bool(np.count_nonzero(xi > x) & 1)


def orient(loops: list[np.ndarray]) -> list[np.ndarray]:
    """Außen gegen, Loch im Uhrzeigersinn – Tiefe der Verschachtelung über Punkt-in-Polygon."""
    out = []
    boxes = [(l[:, 0].min(), l[:, 1].min(), l[:, 0].max(), l[:, 1].max()) for l in loops]
    for i, l in enumerate(loops):
        a = area(l)
        if abs(a) < 1e-9:
            continue
        # Prüfpunkt knapp links/rechts neben einer Kante, damit er sicher nicht auf einem anderen Rand liegt
        pt = (l[0] + l[1]) / 2 if len(l) > 1 else l[0]
        depth = 0
        for j, o in enumerate(loops):
            if j == i:
                continue
            b = boxes[j]
            if b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3] and _inside(pt, o):
                depth += 1
        want_ccw = depth % 2 == 0
        out.append(l if (a > 0) == want_ccw else l[::-1].copy())
    return out


def simplify(p: np.ndarray, min_len: float) -> np.ndarray:
    """Punkte, die näher als min_len am vorigen liegen, weglassen (Central: Mindestvektorlänge)."""
    if len(p) < 3 or min_len <= 0:
        return p
    keep = [0]
    last = p[0]
    for i in range(1, len(p)):
        if (p[i, 0] - last[0]) ** 2 + (p[i, 1] - last[1]) ** 2 >= min_len * min_len:
            keep.append(i)
            last = p[i]
    q = p[keep]
    if len(q) > 2 and np.hypot(*(q[-1] - q[0])) < min_len:
        q = q[:-1]
    return q


def _offset_once(p: np.ndarray, d: float, miter: float):
    e = _nx(p) - p                                        # Kante i: p[i] -> p[i+1]
    ln = np.hypot(e[:, 0], e[:, 1])
    t = e / ln[:, None]
    nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)           # linke Normale = Richtung zum Material
    n_in, n_out = _pv(nrm), nrm                           # einlaufende / auslaufende Kante je Punkt
    m = n_in + n_out
    ml = np.hypot(m[:, 0], m[:, 1])
    ml[ml < 1e-12] = 1e-12
    m /= ml[:, None]
    cos_half = np.einsum("ij,ij->i", m, n_out)
    k = d / np.clip(cos_half, 1.0 / miter, None)          # Gehrungslänge begrenzen (sehr spitze Ecken)
    return p + m * k[:, None], t


def offset_loop(p: np.ndarray, d: float, miter: float = 4.0):
    """Ein ausgerichtetes Polygon um d mm zum Material hin versetzen (d > 0 = nach innen).
    Kanten, die durch den Versatz verschwinden würden (Richtung kehrt sich um), werden entfernt und neu
    gerechnet. Liefert None, wenn vom Polygon nichts übrig bleibt."""
    if d == 0:
        return p.copy()
    p = p.copy()
    a0 = area(p)
    # schnelle Absage: viel zu dünn für den Versatz (2·Fläche/Umfang ~ Inkreisradius)
    if d > 0 and a0 > 0 and 2 * a0 / max(perimeter(p), 1e-12) < d * 0.95:
        return None
    for _ in range(len(p)):
        if len(p) < 3:
            return None
        q, t = _offset_once(p, d, miter)
        qe = _nx(q) - q
        bad = np.einsum("ij,ij->i", qe, t) <= 0           # Kante zeigt nach dem Versatz rückwärts
        if not bad.any():
            break
        # verschwundene Kanten auf je einen Punkt zusammenziehen (mehrere, nicht benachbarte auf einmal)
        n = len(p)
        idx = np.flatnonzero(bad)
        pn = _nx(p)
        lens = np.hypot(*(pn[idx] - p[idx]).T)
        used = np.zeros(n, dtype=bool)
        drop = []
        newpt = {}
        for i in idx[np.argsort(lens)][: max(1, len(idx) // 2)]:
            j = (i + 1) % n
            if used[i] or used[j] or used[(i - 1) % n] or used[(j + 1) % n]:
                continue
            mid = _intersect(p[i - 1], p[i], p[j], p[(j + 1) % n])
            if mid is None or not np.isfinite(mid).all():
                mid = (p[i] + p[j]) / 2
            newpt[i] = mid
            drop.append(j)
            used[i] = used[j] = True
        for i, m in newpt.items():
            p[i] = m
        p = np.delete(p, drop, axis=0)
    else:
        return None
    a1 = area(q)
    if a1 == 0 or (a1 > 0) != (a0 > 0) or abs(a1) < 1e-6:
        return None
    return q


def _intersect(p1, p2, p3, p4):
    """Schnittpunkt der Geraden p1-p2 und p3-p4."""
    d1, d2 = p2 - p1, p4 - p3
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None
    s = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den
    return p1 + s * d1


def offset(loops: list[np.ndarray], d: float, keep_thin: bool = False) -> list[np.ndarray]:
    """Alle (ausgerichteten) Polygone eines Querschnitts um d nach innen versetzen.
    keep_thin: dünne Wände, die beim vollen Versatz verschwinden würden, mit halbem Versatz und notfalls
    auf der Originalkontur behalten (wie die „Edge“-Belichtung bei EOS) – sonst fehlen sie im Druck."""
    out = []
    for l in loops:
        q = offset_loop(l, d)
        if q is None and keep_thin and d > 0:
            q = offset_loop(l, d / 2)
            if q is None and area(l) > 0:        # nur Außenränder, Löcher würden sonst zuwachsen
                q = l.copy()
        if q is not None:
            out.append(q)
    return out


def _rows(loops, spacing, angle):
    """Schnittpunkte der Rastergeraden y = k * spacing im um -angle gedrehten System.
    Liefert [(k, xs sortiert), …] von oben nach unten."""
    c, s = math.cos(-angle), math.sin(-angle)
    xs, ys, xe, ye = [], [], [], []
    for l in loops:
        x = l[:, 0] * c - l[:, 1] * s
        y = l[:, 0] * s + l[:, 1] * c
        xs.append(x); ys.append(y); xe.append(np.roll(x, -1)); ye.append(np.roll(y, -1))
    x0, y0, x1, y1 = (np.concatenate(v) for v in (xs, ys, xe, ye))
    m = y0 != y1
    x0, y0, x1, y1 = x0[m], y0[m], x1[m], y1[m]
    lo, hi = np.minimum(y0, y1), np.maximum(y0, y1)
    k0 = np.ceil(lo / spacing).astype(np.int64)
    k1 = np.ceil(hi / spacing).astype(np.int64) - 1        # halboffen [lo, hi) – Ecken zählen nur einmal
    cnt = np.maximum(0, k1 - k0 + 1)
    if cnt.sum() == 0:
        return []
    rep = np.repeat(np.arange(len(cnt)), cnt)
    k = np.repeat(k0, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
    yy = k * spacing
    xx = x0[rep] + (yy - y0[rep]) * (x1[rep] - x0[rep]) / (y1[rep] - y0[rep])
    order = np.lexsort((xx, k))
    k, xx = k[order], xx[order]
    bounds = np.flatnonzero(np.diff(k)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(k)]])
    return [(int(k[a]), xx[a:b]) for a, b in zip(starts[::-1], ends[::-1])]


def hatch(loops: list[np.ndarray], spacing: float, angle: float, alternating: bool = True,
          min_len: float = 0.0, island: float = 0.0, core=None, core_every: int = 1,
          parity: int = 0) -> list[tuple[float, float, float, float]]:
    """Schraffur wie HatcherLegacy in Central, mit optionalen Erweiterungen.

    Polygone um -angle drehen, mit den Geraden y = k * spacing schneiden (festes Raster durch den
    Ursprung), Schnittpunkte je Gerade nach x sortieren und paarweise verbinden. Die Geraden werden von
    oben (größtes k) nach unten abgearbeitet; die erste Linie läuft von rechts nach links, danach im
    Zickzack. Ergebnis: Strecken (x0, y0, x1, y1) im Druckkoordinatensystem.

    island > 0: Schachbrett aus Quadraten dieser Größe; nur Felder mit (ix + iy) % 2 == parity werden
      in dieser Richtung schraffiert (die anderen Felder mit angle + 90°, siehe hatch_islands).
    core: Funktion (N, 2)-Weltpunkte -> bool „liegt im Kern“; dort bleibt nur jede core_every-te Linie.
    """
    if not loops:
        return []
    cb, sb = math.cos(angle), math.sin(angle)
    return _hatch_fast(loops, spacing, angle, alternating, min_len, island, parity, core, core_every)
    pieces = []                                  # (Feld, k, xa, xb) – alte Fassung, nicht mehr erreicht
    for k, row in _rows(loops, spacing, angle):
        if len(row) % 2:                         # offener Querschnitt – Central überspringt die Linie
            continue
        y = k * spacing
        for i in range(0, len(row), 2):
            xa, xb = float(row[i]), float(row[i + 1])
            spans = [(xa, xb)]
            if core is not None and core_every > 1 and k % core_every:
                spans = _skin_only(spans, y, cb, sb, core)
            if island > 0:
                iy = math.floor(y / island)
                cut = []
                for a, b in spans:
                    ix0, ix1 = math.floor(a / island), math.floor(b / island)
                    for ix in range(ix0, ix1 + 1):
                        if (ix + iy) % 2 != parity:
                            continue
                        pa, pb = max(a, ix * island), min(b, (ix + 1) * island)
                        if pb > pa:
                            cut.append((pa, pb, (iy, ix)))
                spans3 = cut
            else:
                spans3 = [(a, b, (0, 0)) for a, b in spans]
            for a, b, cell in spans3:
                if b - a >= min_len:
                    pieces.append((cell, k, a, b))
    if not pieces:
        return []
    # nach Feldern gruppieren (Felder zeilenweise von oben), in jedem Feld Linien von oben im Zickzack
    cells = {}
    for cell, k, a, b in pieces:
        cells.setdefault(cell, []).append((k, a, b))
    segs = []
    for cell in sorted(cells, key=lambda c: (-c[0], c[1])):
        rows = {}
        for k, a, b in cells[cell]:
            rows.setdefault(k, []).append((a, b))
        forward = False
        for k in sorted(rows, reverse=True):
            y = k * spacing
            pairs = sorted(rows[k])
            pairs = pairs if forward else [(q, p) for p, q in reversed(pairs)]
            for p, q in pairs:
                segs.append((p * cb - y * sb, p * sb + y * cb, q * cb - y * sb, q * sb + y * cb))
            if alternating:
                forward = not forward
    return segs


def _hatch_fast(loops, spacing, angle, alternating, min_len, island=0.0, parity=0, core=None, core_every=1):
    """Schraffur vollständig mit numpy (auch für Haut/Kern und Schachbrett)."""
    c, s = math.cos(-angle), math.sin(-angle)
    pts = [(l[:, 0] * c - l[:, 1] * s, l[:, 0] * s + l[:, 1] * c) for l in loops]
    x0 = np.concatenate([p[0] for p in pts]); y0 = np.concatenate([p[1] for p in pts])
    x1 = np.concatenate([np.roll(p[0], -1) for p in pts]); y1 = np.concatenate([np.roll(p[1], -1) for p in pts])
    m = y0 != y1
    x0, y0, x1, y1 = x0[m], y0[m], x1[m], y1[m]
    lo, hi = np.minimum(y0, y1), np.maximum(y0, y1)
    k0 = np.ceil(lo / spacing).astype(np.int64)
    k1 = np.ceil(hi / spacing).astype(np.int64) - 1
    cnt = np.maximum(0, k1 - k0 + 1)
    tot = int(cnt.sum())
    if tot == 0:
        return []
    rep = np.repeat(np.arange(len(cnt)), cnt)
    k = np.repeat(k0, cnt) + (np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt))
    yy = k * spacing
    xx = x0[rep] + (yy - y0[rep]) * (x1[rep] - x0[rep]) / (y1[rep] - y0[rep])
    order = np.lexsort((xx, -k))                 # Zeilen von oben nach unten, je Zeile x aufsteigend
    k, xx = k[order], xx[order]
    starts = np.flatnonzero(np.r_[True, np.diff(k) != 0])
    lens = np.diff(np.r_[starts, len(k)])
    good_row = lens % 2 == 0                     # offene Querschnitte überspringen (wie Central)
    row_id = np.repeat(np.arange(len(starts)), lens)
    keep = good_row[row_id]
    k, xx, row_id = k[keep], xx[keep], row_id[keep]
    if len(k) == 0:
        return []
    # Zeilen neu nummerieren (nur gültige), Richtung: erste Zeile rückwärts, dann Zickzack
    _, row_n = np.unique(row_id, return_inverse=True)
    a, b = xx[0::2], xx[1::2]
    kr = k[0::2]
    rn = row_n[0::2]
    yv = kr * spacing
    rev = (rn % 2 == 0) if alternating else np.ones(len(rn), dtype=bool)
    # in rückwärts laufenden Zeilen die Paare in umgekehrter Reihenfolge und vertauscht
    pos = np.arange(len(a))
    rstart = np.r_[0, np.flatnonzero(np.diff(rn)) + 1]
    rend = np.r_[rstart[1:], len(a)]
    seq = pos.copy()
    for s0, e0, r in zip(rstart, rend, rev[rstart]):
        if r:
            seq[s0:e0] = pos[s0:e0][::-1]
    a, b, yv, rev = a[seq], b[seq], yv[seq], rev[seq]
    p_ = np.where(rev, b, a)
    q_ = np.where(rev, a, b)
    kk = kr[seq]
    cb, sb = math.cos(angle), math.sin(angle)
    if core is not None and core_every > 1:
        p_, q_, yv, kk = _apply_core(p_, q_, yv, kk, core, core_every, cb, sb)
    if island > 0:
        p_, q_, yv, kk = _apply_islands(p_, q_, yv, kk, island, parity)
    ok = np.abs(q_ - p_) >= min_len
    p_, q_, yv = p_[ok], q_[ok], yv[ok]
    out = np.stack([p_ * cb - yv * sb, p_ * sb + yv * cb, q_ * cb - yv * sb, q_ * sb + yv * cb], axis=1)
    return out


def _apply_core(p_, q_, yv, kk, core, every, cb, sb, step=0.25, min_run=1.0):
    """Im Kern nur jede every-te Linie; auf den übrigen nur die Hautstücke behalten (vektorisiert)."""
    full = (kk % every) == 0
    idx = np.flatnonzero(~full)
    if len(idx) == 0:
        return p_, q_, yv, kk
    P, Q, Y = p_[idx], q_[idx], yv[idx]
    L = np.abs(Q - P)
    ns = np.maximum(2, np.ceil(L / step).astype(int) + 1)
    seg = np.repeat(np.arange(len(idx)), ns)
    first = np.repeat(np.cumsum(ns) - ns, ns)
    t = (np.arange(ns.sum()) - first) / np.repeat(ns - 1, ns)
    xs = P[seg] + (Q[seg] - P[seg]) * t
    ys = Y[seg]
    skin = ~core(np.stack([xs * cb - ys * sb, xs * sb + ys * cb], axis=1))
    newseg = np.r_[True, seg[1:] != seg[:-1]]
    start = skin & (newseg | ~np.r_[False, skin[:-1]])
    endseg = np.r_[seg[1:] != seg[:-1], True]
    end = skin & (endseg | ~np.r_[skin[1:], False])
    si, ei = np.flatnonzero(start), np.flatnonzero(end)
    rp, rq, rseg = xs[si], xs[ei], seg[si]
    keep = np.abs(rq - rp) >= min_run
    rp, rq, rseg = rp[keep], rq[keep], rseg[keep]
    # Ergebnis in der ursprünglichen Reihenfolge zusammensetzen
    orig_pos = np.r_[np.flatnonzero(full), idx[rseg]]
    sub = np.r_[np.zeros(full.sum()), np.arange(len(rseg))]
    P2 = np.r_[p_[full], rp]; Q2 = np.r_[q_[full], rq]
    Y2 = np.r_[yv[full], yv[idx[rseg]]]; K2 = np.r_[kk[full], kk[idx[rseg]]]
    o = np.lexsort((sub, orig_pos))
    return P2[o], Q2[o], Y2[o], K2[o]


def _apply_islands(p_, q_, yv, kk, island, parity):
    """Linien an den Feldgrenzen teilen, nur Felder mit passender Parität behalten, nach Feldern ordnen."""
    lo, hi = np.minimum(p_, q_), np.maximum(p_, q_)
    iy = np.floor(yv / island).astype(np.int64)
    c0 = np.floor(lo / island).astype(np.int64)
    c1 = np.floor(hi / island).astype(np.int64)
    n = c1 - c0 + 1
    rep = np.repeat(np.arange(len(p_)), n)
    off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    fwd = q_ >= p_
    # Felder in Laufrichtung durchnummerieren
    ix = np.where(fwd[rep], c0[rep] + off, c1[rep] - off)
    a = np.maximum(lo[rep], ix * island)
    b = np.minimum(hi[rep], (ix + 1) * island)
    ok = (b > a) & (((ix + iy[rep]) % 2) == parity)
    rep, ix, a, b = rep[ok], ix[ok], a[ok], b[ok]
    P = np.where(fwd[rep], a, b); Q = np.where(fwd[rep], b, a)
    order = np.lexsort((np.arange(len(rep)), ix, -iy[rep]))
    return P[order], Q[order], yv[rep][order], kk[rep][order]


def _skin_only(spans, y, cb, sb, core, step: float = 0.25, min_run: float = 1.0):
    """Teile einer Linie, die NICHT im Kern liegen (Haut), in Schritten von step mm bestimmt."""
    out = []
    for a, b in spans:
        n = max(2, int((b - a) / step) + 1)
        xs = np.linspace(a, b, n)
        pts = np.stack([xs * cb - y * sb, xs * sb + y * cb], axis=1)
        inner = core(pts)
        if not inner.any():
            out.append((a, b))
            continue
        skin = ~inner
        edges = np.flatnonzero(np.diff(skin.astype(np.int8)))
        bounds = np.concatenate([[0], edges + 1, [n]])
        for i0, i1 in zip(bounds[:-1], bounds[1:]):
            # sehr kurze Hautstücke am Rand sind Rasterfehler – weglassen
            if skin[i0] and xs[min(i1, n - 1)] - xs[i0] >= min_run:
                out.append((xs[i0], xs[min(i1, n - 1)]))
    return out


def hatch_islands(loops, spacing, angle, island, **kw):
    """Schachbrett: Felder abwechselnd mit angle und angle + 90° schraffieren."""
    a = np.asarray(hatch(loops, spacing, angle, island=island, parity=0, **kw)).reshape(-1, 4)
    b = np.asarray(hatch(loops, spacing, angle + math.pi / 2, island=island, parity=0, **kw)).reshape(-1, 4)
    return np.concatenate([a, b])


class Raster:
    """Querschnitt als Bitmaske (für Haut/Kern): Gerade-Ungerade-Füllung auf einem Raster."""

    def __init__(self, loops, res: float = 0.25, half: float = 70.0):
        self.res, self.half = res, half
        n = int(2 * half / res)
        self.mask = np.zeros((n, n), dtype=bool)
        for k, row in (_rows(loops, res, 0.0) if loops else []):
            iy = int(round(k + half / res))
            if not 0 <= iy < n or len(row) % 2:
                continue
            for i in range(0, len(row), 2):
                a = int(math.ceil((row[i] + half) / res))
                b = int(math.floor((row[i + 1] + half) / res))
                if b >= a:
                    self.mask[iy, max(0, a):min(n, b + 1)] = True

    def contains(self, pts: np.ndarray) -> np.ndarray:
        ix = np.round((pts[:, 0] + self.half) / self.res).astype(int)
        iy = np.round((pts[:, 1] + self.half) / self.res).astype(int)
        n = self.mask.shape[0]
        ok = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
        out = np.zeros(len(pts), dtype=bool)
        out[ok] = self.mask[iy[ok], ix[ok]]
        return out


def groups(loops: list[np.ndarray]) -> list[list[np.ndarray]]:
    """Ausgerichtete Polygone in Inseln aufteilen: je Außenrand (gegen Uhrzeigersinn) mit seinen Löchern."""
    outers = [l for l in loops if area(l) > 0]
    holes = [l for l in loops if area(l) < 0]
    res = [[o] for o in outers]
    for h in holes:
        best, ba = None, None
        for gi, o in enumerate(outers):
            if _inside(h[0], o):
                a = area(o)
                if ba is None or a < ba:
                    best, ba = gi, a
        if best is not None:
            res[best].append(h)
    return res
