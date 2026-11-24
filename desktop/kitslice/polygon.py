"""Ebene Geometrie eines Querschnitts: Ausrichtung, Versatz (Offset) und Schraffur.

Ein Querschnitt ist eine Liste geschlossener Polygone (np.ndarray (n, 2), erster Punkt nicht wiederholt).
Material liegt nach der Gerade-Ungerade-Regel innen. Nach orient() sind Außenränder gegen den
Uhrzeigersinn und Löcher im Uhrzeigersinn ausgerichtet – das Material liegt dann immer links.
"""
from __future__ import annotations

import math

import numpy as np


def area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


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
    e = np.roll(p, -1, axis=0) - p                        # Kante i: p[i] -> p[i+1]
    ln = np.hypot(e[:, 0], e[:, 1])
    t = e / ln[:, None]
    nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)           # linke Normale = Richtung zum Material
    n_in, n_out = np.roll(nrm, 1, axis=0), nrm            # einlaufende / auslaufende Kante je Punkt
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
    for _ in range(len(p)):
        if len(p) < 3:
            return None
        q, t = _offset_once(p, d, miter)
        qe = np.roll(q, -1, axis=0) - q
        bad = np.einsum("ij,ij->i", qe, t) <= 0           # Kante zeigt nach dem Versatz rückwärts
        if not bad.any():
            break
        # die beiden Endpunkte der kürzesten verschwundenen Kante durch einen ersetzen
        idx = np.flatnonzero(bad)
        i = idx[np.argmin(np.hypot(*(np.roll(p, -1, axis=0)[idx] - p[idx]).T))]
        j = (i + 1) % len(p)
        a, b = p[i - 1], p[(j + 1) % len(p)]
        mid = _intersect(a, p[i], p[j], b)
        if mid is None:
            mid = (p[i] + p[j]) / 2
        p = np.delete(p, j, axis=0)
        p[i if j > i else i - 1] = mid
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


def offset(loops: list[np.ndarray], d: float) -> list[np.ndarray]:
    """Alle (ausgerichteten) Polygone eines Querschnitts um d nach innen versetzen."""
    out = []
    for l in loops:
        q = offset_loop(l, d)
        if q is not None:
            out.append(q)
    return out


def hatch(loops: list[np.ndarray], spacing: float, angle: float, alternating: bool = True,
          min_len: float = 0.0) -> list[tuple[float, float, float, float]]:
    """Schraffur wie HatcherLegacy in Central.

    Polygone um -angle drehen, mit den Geraden y = k * spacing schneiden (festes Raster durch den
    Ursprung), Schnittpunkte je Gerade nach x sortieren und paarweise verbinden. Die Geraden werden von
    oben (größtes k) nach unten abgearbeitet; die erste Linie läuft von rechts nach links, danach im
    Zickzack. Ergebnis: Strecken (x0, y0, x1, y1) im Druckkoordinatensystem.
    """
    if not loops:
        return []
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
    # Geraden von oben nach unten
    bounds = np.flatnonzero(np.diff(k)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(k)]])
    cb, sb = math.cos(angle), math.sin(angle)
    segs = []
    forward = False                                         # erste Linie absteigend in x
    for a, b in zip(starts[::-1], ends[::-1]):
        n = b - a
        if n % 2:          # offener Querschnitt – Central überspringt die Linie ebenfalls
            continue
        y = float(k[a] * spacing)
        row = xx[a:b]
        pairs = [(row[i], row[i + 1]) for i in range(0, n, 2)]
        if not forward:
            pairs = [(q, p) for p, q in reversed(pairs)]
        for p, q in pairs:
            if abs(q - p) < min_len:
                continue
            segs.append((p * cb - y * sb, p * sb + y * cb, q * cb - y * sb, q * sb + y * cb))
        if alternating:
            forward = not forward
    return segs
