"""Auswertung eines Scans des Sintratec-Kalibriermusters („Calibration Pattern v2.0“) für die Laserkorrektur.

Das Muster (Maße aus calibrationPatern2.pdf von Central): drei Quadrate mit halber Kantenlänge 40, 26,67 und
13,33 mm, Achsenkreuz und Diagonalen über ±40 mm, Mitte im Ursprung. Der Kit fährt es aus der Firmware
(Testmuster 1), gebrannt z. B. auf Thermopapier in der Arbeitsebene.

Ablauf:
  1. Grob: Linienpixel finden (dunkel auf hell oder hell auf dunkel), Drehwinkel über die Schärfe der
     Projektionen, Mitte und Maßstab über das Linienkamm-Muster der Projektionen.
  2. Fein: entlang jeder Musterlinie alle 0,5 mm quer zur Linie das Helligkeitsprofil lesen und die
     Linienmitte (Schwerpunkt über halber Höhe) mit Bruchteilen eines Pixels bestimmen. Kreuzungen und
     Ecken werden ausgespart.
  3. Modell: Bildlage F(p) eines Musterpunkts p als Polynom 3. Grades in x, y (je Achse 10 Koeffizienten),
     angepasst über die gemessenen Querabstände (nur senkrecht zur Linie ist die Lage messbar), robust
     gegen Ausreißer, in mehreren Durchgängen mit engerem Suchfenster.
  4. Zerlegen: Lage und Verdrehung des Papiers abziehen (nur zur Info), daraus Maßstab X/Y, Winkligkeit
     und die Restverzerrung N(p). Daraus die Korrekturtabelle für den Pi (kitctl/compensate.py).

Alle Längen in mm. Bild: Graustufen, Zeile 0 oben; intern „Bild-mm“ mit y nach oben.
Ohne Qt, nur numpy – testbar mit künstlich erzeugten Scans.
"""
from __future__ import annotations

import math

import numpy as np

H = (40.0, 80.0 / 3.0, 40.0 / 3.0)        # halbe Kantenlängen der drei Quadrate
EXTENT = 40.0
GRID_STEP, GRID_HALF = 5.0, 55.0


class CalError(ValueError):
    pass


# --------------------------------------------------------------------------------------------- Muster
def segments() -> list[tuple[tuple[float, float], tuple[float, float]]]:
    s = []
    for h in H:
        s += [((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h))]
    s += [((-EXTENT, 0.0), (EXTENT, 0.0)), ((0.0, -EXTENT), (0.0, EXTENT)),
          ((-EXTENT, -EXTENT), (EXTENT, EXTENT)), ((-EXTENT, EXTENT), (EXTENT, -EXTENT))]
    return s


def _crossings() -> np.ndarray:
    """Alle Punkte, an denen sich Musterlinien treffen oder enden."""
    segs = segments()
    pts = []
    for (a, b) in segs:
        pts += [a, b]
    for i in range(len(segs)):
        (x1, y1), (x2, y2) = segs[i]
        for j in range(i + 1, len(segs)):
            (x3, y3), (x4, y4) = segs[j]
            d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(d) < 1e-12:
                continue
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
            u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / d
            if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return np.unique(np.round(np.array(pts), 6), axis=0)


def sample_points(step: float = 0.5, keep_out: float = 1.2):
    """Messstellen auf den Musterlinien: (Punkte p, Richtungen t, Linien-Nr.) ohne Kreuzungsnähe."""
    cr = _crossings()
    P, T, S = [], [], []
    for k, ((x1, y1), (x2, y2)) in enumerate(segments()):
        L = math.hypot(x2 - x1, y2 - y1)
        n = int(L / step)
        ts = (np.arange(n) + 0.5) / n
        p = np.stack([x1 + ts * (x2 - x1), y1 + ts * (y2 - y1)], 1)
        d = np.min(np.hypot(p[:, None, 0] - cr[None, :, 0], p[:, None, 1] - cr[None, :, 1]), 1)
        p = p[d > keep_out]
        P.append(p)
        T.append(np.tile([(x2 - x1) / L, (y2 - y1) / L], (len(p), 1)))
        S.append(np.full(len(p), k))
    return np.concatenate(P), np.concatenate(T), np.concatenate(S)


# --------------------------------------------------------------------------------------------- Modell
def _basis(p: np.ndarray, deg: int) -> np.ndarray:
    x, y = p[:, 0] / EXTENT, p[:, 1] / EXTENT
    cols = [np.ones_like(x)]
    for d in range(1, deg + 1):
        for i in range(d + 1):
            cols.append(x ** (d - i) * y ** i)
    return np.stack(cols, 1)


def _dbasis(p: np.ndarray, deg: int):
    """Ableitungen der Basis nach x und y (in mm)."""
    x, y = p[:, 0] / EXTENT, p[:, 1] / EXTENT
    dx, dy = [np.zeros_like(x)], [np.zeros_like(x)]
    for d in range(1, deg + 1):
        for i in range(d + 1):
            a, b = d - i, i
            dx.append((a * x ** (a - 1) if a else 0 * x) * y ** b / EXTENT)
            dy.append(x ** a * (b * y ** (b - 1) if b else 0 * y) / EXTENT)
    return np.stack(dx, 1), np.stack(dy, 1)


class Poly:
    """F(p) = [Φ(p)·a, Φ(p)·b] – Lage im Bild (Bild-mm) eines Musterpunkts p."""

    def __init__(self, a: np.ndarray, b: np.ndarray, deg: int):
        self.a, self.b, self.deg = np.asarray(a, float), np.asarray(b, float), deg

    @classmethod
    def affine(cls, A: np.ndarray, t: np.ndarray) -> "Poly":
        # Basis 1, x/E, y/E
        return cls(np.array([t[0], A[0, 0] * EXTENT, A[0, 1] * EXTENT]),
                   np.array([t[1], A[1, 0] * EXTENT, A[1, 1] * EXTENT]), 1)

    def __call__(self, p: np.ndarray) -> np.ndarray:
        B = _basis(np.atleast_2d(p), self.deg)
        return np.stack([B @ self.a, B @ self.b], 1)

    def jac(self, p: np.ndarray) -> np.ndarray:
        dx, dy = _dbasis(np.atleast_2d(p), self.deg)
        return np.stack([np.stack([dx @ self.a, dy @ self.a], 1), np.stack([dx @ self.b, dy @ self.b], 1)], 1)


# --------------------------------------------------------------------------------------------- Bild
def _to_float(img: np.ndarray) -> np.ndarray:
    a = np.asarray(img)
    if a.ndim == 3:
        a = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    return a.astype(np.float32)


def _block_mean(a: np.ndarray, f: int) -> np.ndarray:
    if f <= 1:
        return a
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean((1, 3))


def _background(a: np.ndarray, tile: int, q: float) -> np.ndarray:
    """Hintergrund als Perzentil je Kachel, weich hochgerechnet."""
    h, w = a.shape
    th, tw = max(1, math.ceil(h / tile)), max(1, math.ceil(w / tile))
    pad = np.pad(a, ((0, th * tile - h), (0, tw * tile - w)), mode="edge")
    t = np.percentile(pad.reshape(th, tile, tw, tile).transpose(0, 2, 1, 3).reshape(th, tw, -1), q, axis=2)
    ys = (np.arange(h) + 0.5) / tile - 0.5
    xs = (np.arange(w) + 0.5) / tile - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, th - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, tw - 1)
    y1, x1 = np.minimum(y0 + 1, th - 1), np.minimum(x0 + 1, tw - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None]
    fx = np.clip(xs - x0, 0, 1)[None, :]
    return (t[y0][:, x0] * (1 - fy) * (1 - fx) + t[y0][:, x1] * (1 - fy) * fx
            + t[y1][:, x0] * fy * (1 - fx) + t[y1][:, x1] * fy * fx)


def _bilinear(img: np.ndarray, col: np.ndarray, row: np.ndarray) -> np.ndarray:
    h, w = img.shape
    c = np.clip(col, 0, w - 1.001)
    r = np.clip(row, 0, h - 1.001)
    c0, r0 = c.astype(np.int64), r.astype(np.int64)
    fc, fr = c - c0, r - r0
    v = (img[r0, c0] * (1 - fc) * (1 - fr) + img[r0, c0 + 1] * fc * (1 - fr)
         + img[r0 + 1, c0] * (1 - fc) * fr + img[r0 + 1, c0 + 1] * fc * fr)
    out = (col < 0) | (row < 0) | (col > w - 1) | (row > h - 1)
    v[out] = np.nan
    return v


# --------------------------------------------------------------------------------------------- Grobsuche
_COMB = np.array([-H[0], -H[1], -H[2], 0.0, H[2], H[1], H[0]])


def _comb(hist: np.ndarray, x0: float, binw: float):
    """Beste Mitte und Maßstab eines Linienkamms (7 Linien) in einer Projektion."""
    k = np.exp(-0.5 * (np.arange(-6, 7) * binw / 0.3) ** 2)
    hs = np.convolve(hist, k / k.sum(), mode="same")
    xs = x0 + (np.arange(len(hs)) + 0.5) * binw
    best = (-1.0, 0.0, 1.0)
    for s in np.arange(0.9, 1.1001, 0.0025):
        lo, hi = xs[0] + s * H[0], xs[-1] - s * H[0]
        if hi <= lo:
            continue
        cs = np.arange(lo, hi, binw * 0.5)
        pos = cs[:, None] + s * _COMB[None, :]
        sc = np.interp(pos, xs, hs).sum(1)
        i = int(np.argmax(sc))
        if sc[i] > best[0]:
            best = (float(sc[i]), float(cs[i]), float(s))
    # Verfeinern
    _, c, s = best
    for _ in range(2):
        for s2 in np.linspace(s - 0.004, s + 0.004, 17):
            cs = np.linspace(c - binw, c + binw, 21)
            sc = np.interp(cs[:, None] + s2 * _COMB[None, :], xs, hs).sum(1)
            i = int(np.argmax(sc))
            if sc[i] > best[0]:
                best = (float(sc[i]), float(cs[i]), float(s2))
        _, c, s = best
    peak = best[0] / (7 * max(hs.max(), 1e-9))
    return best[1], best[2], peak


def _coarse(g: np.ndarray, ppm: float, dark: bool):
    f = max(1, int(round(ppm / 6.0)))
    small = _block_mean(g, f)
    ps = ppm / f
    tile = max(8, int(round(5 * ps)))
    if dark:
        d = _background(small, tile, 90) - small
    else:
        d = small - _background(small, tile, 10)
    c = np.percentile(d, 99.7)
    if c <= 1e-6:
        return None
    ys, xs = np.nonzero(d > 0.4 * c)
    if len(xs) < 200:
        return None
    if len(xs) > 400000:
        sel = np.random.default_rng(1).choice(len(xs), 400000, replace=False)
        ys, xs = ys[sel], xs[sel]
    h = small.shape[0]
    u = (xs + 0.5) / ps
    v = (h - ys - 0.5) / ps
    binw = 0.25

    def score(th):
        ct, st = math.cos(th), math.sin(th)
        a = u * ct + v * st
        b = -u * st + v * ct
        ha = np.bincount(((a - a.min()) / binw).astype(int)).astype(float)
        hb = np.bincount(((b - b.min()) / binw).astype(int)).astype(float)
        return (ha ** 2).sum() + (hb ** 2).sum()
    ths = np.radians(np.arange(-12.0, 12.0001, 0.1))
    sc = [score(t) for t in ths]
    t0 = ths[int(np.argmax(sc))]
    ths = t0 + np.radians(np.arange(-0.12, 0.12001, 0.01))
    sc = [score(t) for t in ths]
    th = float(ths[int(np.argmax(sc))])
    ct, st = math.cos(th), math.sin(th)
    a = u * ct + v * st
    b = -u * st + v * ct
    bw = 0.1
    ha = np.bincount(((a - a.min()) / bw).astype(int)).astype(float)
    hb = np.bincount(((b - b.min()) / bw).astype(int)).astype(float)
    ca, sa, pa = _comb(ha, a.min(), bw)
    cb, sb, pb = _comb(hb, b.min(), bw)
    R = np.array([[ct, -st], [st, ct]])
    A = R @ np.diag([sa, sb])
    t = R @ np.array([ca, cb])
    return {"poly": Poly.affine(A, t), "theta": th, "quality": min(pa, pb), "line_px": len(xs)}


# --------------------------------------------------------------------------------------------- Feinmessung
def _measure(g: np.ndarray, ppm: float, dark: bool, F: Poly, P, T, half: float):
    """Querprofile an allen Messstellen; liefert Normalen n, gemessene Punkte m (Bild-mm), Linienbreite, gültig."""
    h = g.shape[0]
    q = F(P)
    J = F.jac(P)
    t = np.einsum("nij,nj->ni", J, T)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    n = np.stack([-t[:, 1], t[:, 0]], 1)
    step = 1.0 / ppm
    offs = np.arange(-half, half + step * 0.5, step)
    pu = q[:, None, 0] + offs[None, :] * n[:, None, 0]
    pv = q[:, None, 1] + offs[None, :] * n[:, None, 1]
    prof = _bilinear(g, pu * ppm - 0.5, (h - 0.5) - pv * ppm)
    if dark:
        prof = -prof
    M = len(offs)
    e = max(2, M // 7)
    m = np.full(len(P), np.nan)
    width = np.full(len(P), np.nan)
    ok = ~np.isnan(prof).any(1)
    left = np.nanmean(prof[:, :e], 1)
    right = np.nanmean(prof[:, -e:], 1)
    noise = np.nanstd(np.concatenate([prof[:, :e] - left[:, None], prof[:, -e:] - right[:, None]], 1), 1)
    base = left[:, None] + (right - left)[:, None] * np.linspace(0, 1, M)[None, :]
    d = prof - base
    for i in np.nonzero(ok)[0]:
        row = d[i]
        k = int(np.argmax(row))
        pk = row[k]
        if pk < max(8.0 * noise[i], 1e-6) or k < e or k > M - 1 - e:
            continue
        half_v = 0.5 * pk
        lo = k
        while lo > 0 and row[lo - 1] > half_v:
            lo -= 1
        hi = k
        while hi < M - 1 and row[hi + 1] > half_v:
            hi += 1
        if lo <= 1 or hi >= M - 2:
            continue
        w = row[lo:hi + 1] - half_v
        m[i] = float((w * offs[lo:hi + 1]).sum() / w.sum())
        # Breite über halber Höhe mit Teilpixeln an beiden Flanken
        fl = (row[lo] - half_v) / max(row[lo] - row[lo - 1], 1e-9)
        fr = (row[hi] - half_v) / max(row[hi] - row[hi + 1], 1e-9)
        width[i] = (hi - lo + fl + fr) * step
    good = ~np.isnan(m)
    meas = q + m[:, None] * n
    return n, meas, width, good


def _fit(P, n, meas, deg: int, ridge: float = 0.5) -> tuple[Poly, np.ndarray]:
    B = _basis(P, deg)
    A = np.concatenate([n[:, :1] * B, n[:, 1:] * B], 1)
    y = (n * meas).sum(1)
    nb = B.shape[1]
    nl = [i for i in range(nb) if i >= 3]          # Terme 2. und 3. Grades leicht dämpfen
    if nl and deg > 1:
        Rg = np.zeros((2 * len(nl), 2 * nb))
        for r, i in enumerate(nl):
            Rg[r, i] = ridge
            Rg[len(nl) + r, nb + i] = ridge
        A2 = np.concatenate([A, Rg])
        y2 = np.concatenate([y, np.zeros(len(Rg))])
    else:
        A2, y2 = A, y
    coef, *_ = np.linalg.lstsq(A2, y2, rcond=None)
    F = Poly(coef[:nb], coef[nb:], deg)
    res = y - A @ coef
    return F, res


# --------------------------------------------------------------------------------------------- Auswerten
def analyze(img: np.ndarray, ppm: float, rot90: int = 0, polarity: str = "auto") -> dict:
    """Einen Scan auswerten. img: Graustufen (oder RGB), ppm: Pixel je mm, rot90: Viertelumdrehungen im
    Uhrzeigersinn, damit Laser-X nach rechts zeigt. Ergebnis siehe Docstring des Moduls / _result()."""
    if not (2.0 <= ppm <= 200.0):
        raise CalError("Auflösung unplausibel – bitte dpi prüfen")
    g = _to_float(img)
    if rot90 % 4:
        g = np.ascontiguousarray(np.rot90(g, k=-(rot90 % 4)))
    hmm, wmm = g.shape[0] / ppm, g.shape[1] / ppm
    if min(hmm, wmm) < 85:
        raise CalError(f"Scan zu klein ({wmm:.0f} × {hmm:.0f} mm) – das Muster ist 80 × 80 mm, bitte mit Rand scannen")
    cands = []
    for dark in ((True, False) if polarity == "auto" else ((polarity != "light"),)):
        c = _coarse(g, ppm, dark)
        if c:
            c["dark"] = dark
            cands.append(c)
    if not cands:
        raise CalError("Kein Muster gefunden – Linien zu schwach oder Bild leer")
    co = max(cands, key=lambda c: c["quality"])
    if co["quality"] < 0.25:
        raise CalError("Muster nicht sicher erkannt – Scan, Ausrichtung (±12°) und dpi prüfen")
    dark = co["dark"]
    F = co["poly"]
    res = np.zeros(0)
    widths = np.array([0.3])
    stages = ((2.5, 1), (1.5, 3), (1.0, 3), (None, 3), (None, 3))
    for it, (half_i, deg_i) in enumerate(stages):
        if half_i is None:
            wmed = float(np.nanmedian(widths)) if np.isfinite(widths).any() else 0.3
            half_i = float(np.clip(1.6 * wmed + 0.25, 0.45, 1.2))
        # Abstand zu Kreuzungen > Suchfenster: sonst läge eine schräg kreuzende Linie (Diagonale) im Profil
        P, T, S = sample_points(0.5, max(1.6, half_i + 0.4))
        n, meas, widths, good = _measure(g, ppm, dark, F, P, T, half_i)
        if good.sum() < 200:
            raise CalError("Zu wenige Linienstellen gemessen – Scan unscharf oder Muster nicht vollständig")
        idx = np.nonzero(good)[0]
        Fi, r = _fit(P[idx], n[idx], meas[idx], deg_i)
        if it >= 3:
            for _ in range(3):                      # robust: Ausreißer (Flecken, Knicke, Papierrand) raus
                mad = 1.4826 * np.median(np.abs(r - np.median(r)))
                keep = np.abs(r) <= max(4 * mad, 0.012)
                if keep.all():
                    break
                idx = idx[keep]
                Fi, r = _fit(P[idx], n[idx], meas[idx], deg_i)
        F = Fi
        used = np.zeros(len(P), bool)
        used[idx] = True
        res = r
    cover = np.bincount(S[used], minlength=len(segments())) / np.maximum(np.bincount(S, minlength=len(segments())), 1)
    if (cover < 0.3).sum() > 2:
        raise CalError("Teile des Musters fehlen im Scan oder sind zu schwach – bitte vollständig und kontrastreich scannen")
    return _result(F, res, used, widths, cover, dark, co["theta"])


def _result(F: Poly, res, used, widths, cover, dark, theta) -> dict:
    J0 = F.jac(np.zeros((1, 2)))[0]
    th0 = math.atan2(J0[1, 0], J0[0, 0])
    c0 = F(np.zeros((1, 2)))[0]
    Rm = np.array([[math.cos(-th0), -math.sin(-th0)], [math.sin(-th0), math.cos(-th0)]])
    L = Rm @ J0
    sx = float(L[0, 0])
    sy = float(math.hypot(L[0, 1], L[1, 1]))
    skew = float(math.degrees(math.atan2(-L[0, 1], L[1, 1])))
    # Maschinenmodell F_m(p) = R(−θ)(F(p) − F(0)) als Polynom-Koeffizienten
    a = Rm[0, 0] * F.a + Rm[0, 1] * F.b
    b = Rm[1, 0] * F.a + Rm[1, 1] * F.b
    a[0] = b[0] = 0.0                                   # F(0) = Konstante -> Lage des Papiers abgezogen
    Fm = Poly(a, b, F.deg)
    Lm = np.array([[sx, L[0, 1]], [0.0, L[1, 1]]])
    gx = np.linspace(-EXTENT, EXTENT, 33)
    pts = np.stack(np.meshgrid(gx, gx), -1).reshape(-1, 2)
    N = Fm(pts) - pts @ Lm.T
    nl_max = float(np.max(np.hypot(N[:, 0], N[:, 1]))) * 1000
    return {
        "ok": True,
        "model": {"a": Fm.a.tolist(), "b": Fm.b.tolist(), "deg": Fm.deg},
        "scale_x_pct": (sx - 1) * 100,
        "scale_y_pct": (sy - 1) * 100,
        "skew_deg": skew,
        "rotation_deg": math.degrees(th0),
        "center_mm": [float(c0[0]), float(c0[1])],
        "nonlinear_max_um": nl_max,
        "rms_um": float(np.sqrt(np.mean(res ** 2)) * 1000) if len(res) else 0.0,
        "samples": int(used.sum()),
        "line_width_mm": float(np.nanmedian(widths)) if np.isfinite(widths).any() else 0.0,
        "coverage_min": float(cover.min()),
        "polarity": "dark" if dark else "light",
    }


def model_of(r: dict) -> Poly:
    m = r["model"]
    return Poly(np.array(m["a"]), np.array(m["b"]), int(m["deg"]))


def _linear(Fm: Poly) -> np.ndarray:
    J = Fm.jac(np.zeros((1, 2)))[0]
    return np.array([[J[0, 0], J[0, 1]], [0.0, J[1, 1]]])


def combine(results: list[dict]) -> dict:
    """Mehrere Scans (z. B. 0° und 90° gedreht gescannt) mitteln: Schiefe und Verzug des Scanners heben sich auf."""
    if not results:
        raise CalError("Kein Scan ausgewertet")
    deg = max(int(r["model"]["deg"]) for r in results)
    nb = _basis(np.zeros((1, 2)), deg).shape[1]

    def pad(v):
        v = np.asarray(v, float)
        return np.concatenate([v, np.zeros(nb - len(v))])
    a = np.mean([pad(r["model"]["a"]) for r in results], 0)
    b = np.mean([pad(r["model"]["b"]) for r in results], 0)
    out = dict(results[0])
    out["model"] = {"a": a.tolist(), "b": b.tolist(), "deg": deg}
    Fm = Poly(a, b, deg)
    L = _linear(Fm)
    out["scale_x_pct"] = (L[0, 0] - 1) * 100
    out["scale_y_pct"] = (math.hypot(L[0, 1], L[1, 1]) - 1) * 100
    out["skew_deg"] = math.degrees(math.atan2(-L[0, 1], L[1, 1]))
    out["rms_um"] = float(np.sqrt(np.mean([r["rms_um"] ** 2 for r in results])))
    out["samples"] = int(sum(r["samples"] for r in results))
    out["scans"] = len(results)
    gx = np.linspace(-EXTENT, EXTENT, 33)
    pts = np.stack(np.meshgrid(gx, gx), -1).reshape(-1, 2)
    N = Fm(pts) - pts @ L.T
    out["nonlinear_max_um"] = float(np.max(np.hypot(N[:, 0], N[:, 1]))) * 1000
    if len(results) > 1:
        out["spread"] = {k: float(np.ptp([r[k] for r in results])) for k in ("scale_x_pct", "scale_y_pct", "skew_deg")}
    return out


def compensation(result: dict, use_scale: bool = True, use_grid: bool = True) -> dict:
    """Werte für den Pi (kitctl/compensate.py) aus einem Ergebnis von analyze()/combine().

    Gesucht ist für jeden Sollpunkt d der befohlene Punkt c mit F_m(c) = S·d (S = 1, oder ohne Maßstab der
    gemessene Maßstab, der dann weiter über die Skalierung im Kit läuft). Am Pi gilt c = L'⁻¹(d + R(d));
    daraus R(d) = L'·c − d. Außerhalb des Musters (±40 mm) wird die Restverzerrung am Rand festgehalten.
    """
    Fm = model_of(result)
    L = _linear(Fm)
    sx, sy = L[0, 0], math.hypot(L[0, 1], L[1, 1])
    eps = math.atan2(-L[0, 1], L[1, 1])
    if use_scale:
        Lp = L
        S = np.eye(2)
    else:
        Lp = np.array([[1.0, -math.sin(eps)], [0.0, math.cos(eps)]])
        S = np.diag([sx, sy])
    comp = {"enabled": True,
            "scale_x_pct": round((sx - 1) * 100, 5) if use_scale else 0.0,
            "scale_y_pct": round((sy - 1) * 100, 5) if use_scale else 0.0,
            "skew_deg": round(math.degrees(eps), 5),
            "lean_x_mm_per_100": 0.0, "lean_y_mm_per_100": 0.0, "grid": None}
    if use_grid and Fm.deg > 1:
        n = int(round(2 * GRID_HALF / GRID_STEP)) + 1
        gx = np.linspace(-GRID_HALF, GRID_HALF, n)
        d = np.stack(np.meshgrid(gx, gx), -1).reshape(-1, 2)        # Zeilen = y, Spalten = x
        target = d @ S.T
        Li = np.linalg.inv(L)

        def nonlin(c):
            cc = np.clip(c, -EXTENT - 1.65, EXTENT + 1.65)
            return Fm(cc) - cc @ L.T
        c = target @ Li.T
        for _ in range(30):
            c_new = (target - nonlin(c)) @ Li.T
            if np.max(np.abs(c_new - c)) < 1e-7:
                c = c_new
                break
            c = c_new
        R = c @ Lp.T - d
        if np.max(np.abs(R)) > 1e-4:
            comp["grid"] = {"step": GRID_STEP, "half": GRID_HALF,
                            "dx": np.round(R[:, 0].reshape(n, n), 5).tolist(),
                            "dy": np.round(R[:, 1].reshape(n, n), 5).tolist()}
    return comp


def deviation_lines(result: dict, step: float = 1.0) -> list[list[list[float]]]:
    """Für die Grafik: je Musterlinie Punkte [x, y, dx, dy] – Abweichung F_m(p) − p in mm."""
    Fm = model_of(result)
    out = []
    for (x1, y1), (x2, y2) in segments():
        L = math.hypot(x2 - x1, y2 - y1)
        k = max(2, int(L / step) + 1)
        ts = np.linspace(0, 1, k)
        p = np.stack([x1 + ts * (x2 - x1), y1 + ts * (y2 - y1)], 1)
        d = Fm(p) - p
        out.append(np.round(np.concatenate([p, d], 1), 5).tolist())
    return out


# --------------------------------------------------------------------------------------------- Testbilder
def synth(ppm: float, forward=None, size_mm: float = 100.0, width_mm: float = 0.28, rot_deg: float = 0.0,
          shift=(0.0, 0.0), dark: bool = True, noise: float = 3.0, seed: int = 0) -> np.ndarray:
    """Künstlicher Scan: Muster durch forward(p) -> p' (mm, Laserfehler) verzerrt, dann Papier gedreht und
    verschoben. Graustufen uint8, Linien dunkel (Thermopapier) oder hell (Cyanotypie)."""
    rng = np.random.default_rng(seed)
    n = int(round(size_mm * ppm))
    acc = np.zeros((n, n), np.float32)
    sig = width_mm / 2.355
    r = int(math.ceil(3 * sig * ppm)) + 1
    oy, ox = np.mgrid[-r:r + 1, -r:r + 1]
    ct, st = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    spacing = min(0.02, 0.5 / ppm)
    for (x1, y1), (x2, y2) in segments():
        L = math.hypot(x2 - x1, y2 - y1)
        ts = np.linspace(0, 1, int(L / spacing) + 1)
        p = np.stack([x1 + ts * (x2 - x1), y1 + ts * (y2 - y1)], 1)
        if forward is not None:
            p = forward(p)
        u = ct * p[:, 0] - st * p[:, 1] + size_mm / 2 + shift[0]
        v = st * p[:, 0] + ct * p[:, 1] + size_mm / 2 + shift[1]
        col = u * ppm - 0.5
        row = (n - 0.5) - v * ppm
        ci, ri = np.round(col).astype(int), np.round(row).astype(int)
        fc, fr = col - ci, row - ri
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                w = np.exp(-((dx - fc) ** 2 + (dy - fr) ** 2) / (2 * (sig * ppm) ** 2)).astype(np.float32)
                yy, xx = ri + dy, ci + dx
                ok = (yy >= 0) & (yy < n) & (xx >= 0) & (xx < n)
                np.add.at(acc, (yy[ok], xx[ok]), w[ok])
    acc *= spacing * ppm / (math.sqrt(2 * math.pi) * sig * ppm)
    ink = 1 - np.exp(-2.5 * acc)
    bg = 225 + 15 * np.linspace(-1, 1, n)[None, :]                     # leichter Helligkeitsverlauf
    if dark:
        img = bg - 190 * ink
    else:
        img = 70 + 120 * ink + 0 * bg
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)
