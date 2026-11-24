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
    pieces = []                                  # (Feld, k, xa, xb)
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
    a = hatch(loops, spacing, angle, island=island, parity=0, **kw)
    b = hatch(loops, spacing, angle + math.pi / 2, island=island, parity=0, **kw)
    return a + b


class Raster:
    """Querschnitt als Bitmaske (für Haut/Kern): Gerade-Ungerade-Füllung auf einem Raster."""

    def __init__(self, loops, res: float = 0.25, half: float = 70.0):
        self.res, self.half = res, half
        n = int(2 * half / res)
        self.mask = np.zeros((n, n), dtype=bool)
        for k, row in _rows(loops, res, 0.0):
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
