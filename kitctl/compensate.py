"""Laserkorrektur: rechnet jeden Laserpunkt eines Druckjobs um, bevor er zum Kit geht.

Gespeichert ist der *gemessene Fehler* des Kits (Auswertung des Kalibriermusters in Kit Control):
  scale_x_pct, scale_y_pct   gebrannt = (1 + pct/100) × befohlen, je Achse
  skew_deg                   Winkel zwischen gebrannter X- und Y-Achse minus 90°
                             (positiv = Achsen stehen offener als 90°)
  lean_x_mm_per_100,         Versatz der Teile je 100 mm Bauhöhe (Schräglauf der Bauplattform)
  lean_y_mm_per_100
  grid                       Restverzerrung als Tabelle {"step", "half", "dx", "dy"} (mm, Zeilen = Y von −half
                             bis +half, Spalten = X); dazwischen bilinear, außerhalb der Randwert

Korrektur für einen Sollpunkt d in Schichthöhe z:
  d' = d − lean · z / 100
  c  = L⁻¹ · (d' + R(d'))      mit L = [[sx, −sy·sin ε], [0, sy·cos ε]] und R aus der Tabelle
Steht alles auf 0 (oder ist die Korrektur aus), bleibt die Datei Byte für Byte unverändert.

Mit Tabelle kann eine gerade Linie nach der Korrektur leicht gebogen sein. Dann wird sie halbiert, bis die
Abweichung zwischen Sehne und Bogen unter TOL_MM liegt (meist gar nicht oder in wenige Stücke) – nie
unnötig viele kurze Vektoren, die den Laser bremsen würden. Sprünge (Laser aus) werden nicht zerlegt.
Nur Standardbibliothek (der Pi hat kein numpy).
"""
from __future__ import annotations

import math
import struct

from kitctl import pjob

TOL_MM = 0.005             # erlaubte Abweichung einer zerlegten Linie vom korrigierten Bogen
MIN_PIECE_MM = 0.5
MAX_DEPTH = 8
LIMIT_UM = 55000            # Central clippt auf ±55 mm
ZERO = {"enabled": True, "scale_x_pct": 0.0, "scale_y_pct": 0.0, "skew_deg": 0.0,
        "lean_x_mm_per_100": 0.0, "lean_y_mm_per_100": 0.0, "grid": None}
LIMITS = {"scale_x_pct": 5.0, "scale_y_pct": 5.0, "skew_deg": 3.0,
          "lean_x_mm_per_100": 5.0, "lean_y_mm_per_100": 5.0}
GRID_MAX_MM = 2.0


def _grid_ok(g) -> bool:
    return bool(g) and isinstance(g, dict) and g.get("dx") and g.get("dy")


def grid_nonzero(g) -> bool:
    if not _grid_ok(g):
        return False
    return any(abs(v) > 1e-6 for row in g["dx"] for v in row) or any(abs(v) > 1e-6 for row in g["dy"] for v in row)


def active(c: dict | None) -> bool:
    if not c or not c.get("enabled", True):
        return False
    return any(abs(float(c.get(k) or 0)) > 1e-9 for k in LIMITS) or grid_nonzero(c.get("grid"))


def validate(c: dict) -> dict:
    """Geprüfte, vollständige Kopie – wirft ValueError bei unsinnigen Werten."""
    if not isinstance(c, dict):
        raise ValueError("Korrektur muss ein Objekt sein")
    out = dict(ZERO)
    out["enabled"] = bool(c.get("enabled", True))
    for k, lim in LIMITS.items():
        v = float(c.get(k) or 0.0)
        if not math.isfinite(v) or abs(v) > lim:
            raise ValueError(f"{k} außerhalb ±{lim:g}")
        out[k] = v
    g = c.get("grid")
    if g:
        step, half = float(g.get("step", 5.0)), float(g.get("half", 55.0))
        if not (1.0 <= step <= 20.0 and 20.0 <= half <= 60.0):
            raise ValueError("Korrekturtabelle: Raster ungültig")
        n = int(round(2 * half / step)) + 1
        if abs((n - 1) * step - 2 * half) > 1e-6 or n > 61:
            raise ValueError("Korrekturtabelle: Raster ungültig")
        for key in ("dx", "dy"):
            rows = g.get(key)
            if not isinstance(rows, list) or len(rows) != n or any(not isinstance(r, list) or len(r) != n for r in rows):
                raise ValueError(f"Korrekturtabelle: {key} muss {n}×{n} Werte haben")
            for r in rows:
                for v in r:
                    v = float(v)
                    if not math.isfinite(v) or abs(v) > GRID_MAX_MM:
                        raise ValueError(f"Korrekturtabelle: Wert außerhalb ±{GRID_MAX_MM:g} mm")
        out["grid"] = {"step": step, "half": half,
                       "dx": [[round(float(v), 5) for v in r] for r in g["dx"]],
                       "dy": [[round(float(v), 5) for v in r] for r in g["dy"]]}
    for k in ("info", "updated"):
        if k in c:
            out[k] = c[k]
    return out


class Transform:
    """Sollpunkt (mm) in Schichthöhe z (mm) -> befohlener Punkt (mm)."""

    def __init__(self, c: dict):
        sx = 1 + float(c.get("scale_x_pct") or 0) / 100
        sy = 1 + float(c.get("scale_y_pct") or 0) / 100
        e = math.radians(float(c.get("skew_deg") or 0))
        # L = [[sx, -sy sin e], [0, sy cos e]]  ->  L⁻¹
        a, b, d = sx, -sy * math.sin(e), sy * math.cos(e)
        self.ia, self.ib, self.id = 1 / a, -b / (a * d), 1 / d
        self.lx = float(c.get("lean_x_mm_per_100") or 0) / 100
        self.ly = float(c.get("lean_y_mm_per_100") or 0) / 100
        g = c.get("grid")
        self.grid = g if grid_nonzero(g) else None
        if self.grid:
            self.step, self.half = float(g["step"]), float(g["half"])
            self.n = len(g["dx"])
            self.gx, self.gy = g["dx"], g["dy"]

    def _r(self, x: float, y: float):
        n, s, h = self.n, self.step, self.half
        fx = min(max((x + h) / s, 0.0), n - 1.0)
        fy = min(max((y + h) / s, 0.0), n - 1.0)
        i, j = min(int(fx), n - 2), min(int(fy), n - 2)
        tx, ty = fx - i, fy - j
        gx, gy = self.gx, self.gy
        w00, w10, w01, w11 = (1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty
        rx = gx[j][i] * w00 + gx[j][i + 1] * w10 + gx[j + 1][i] * w01 + gx[j + 1][i + 1] * w11
        ry = gy[j][i] * w00 + gy[j][i + 1] * w10 + gy[j + 1][i] * w01 + gy[j + 1][i + 1] * w11
        return rx, ry

    def __call__(self, x: float, y: float, z: float = 0.0):
        x -= self.lx * z
        y -= self.ly * z
        if self.grid:
            rx, ry = self._r(x, y)
            x += rx
            y += ry
        return self.ia * x + self.ib * y, self.id * y


def _clamp(v: float) -> int:
    v = int(math.floor(v * 1000 + 0.5))
    return LIMIT_UM if v > LIMIT_UM else -LIMIT_UM if v < -LIMIT_UM else v


def apply(data: bytes, c: dict | None) -> tuple[bytes, dict]:
    """Korrigierte Druckdatei und eine kleine Statistik. Ohne aktive Korrektur: data unverändert."""
    if not active(c):
        return data, {"applied": False}
    tf = Transform(c)
    split = tf.grid is not None
    out = bytearray(data[:pjob.HEADER])
    pack = struct.Struct("<Hii").pack
    z = 0.0
    px = py = 0.0                   # zuletzt angefahrener Sollpunkt (mm)
    pc = tf(0.0, 0.0, 0.0)          # … und sein korrigierter Punkt
    n_in = n_out = 0
    max_shift = 0.0

    def pieces(ax, ay, ca, bx, by, cb, depth):
        """Zwischenpunkte (korrigiert) zwischen a und b, damit die Linie dem Bogen folgt; ohne b selbst."""
        mx, my = (ax + bx) / 2, (ay + by) / 2
        cm = tf(mx, my, z)
        dev = math.hypot(cm[0] - (ca[0] + cb[0]) / 2, cm[1] - (ca[1] + cb[1]) / 2)
        if dev <= TOL_MM or depth >= MAX_DEPTH or math.hypot(bx - ax, by - ay) < 2 * MIN_PIECE_MM:
            return []
        return pieces(ax, ay, ca, mx, my, cm, depth + 1) + [cm] + pieces(mx, my, cm, bx, by, cb, depth + 1)

    for pos, code, body in pjob._records(data):
        if code == pjob.GO or code == pjob.JUMP:
            xi, yi = struct.unpack("<ii", body)
            x, y = xi / 1000, yi / 1000
            n_in += 1
            cx, cy = tf(x, y, z)
            if split and code == pjob.GO:
                for qx, qy in pieces(px, py, pc, x, y, (cx, cy), 0):
                    out += pack(code, _clamp(qx), _clamp(qy))
                    n_out += 1
            sh = math.hypot(cx - x, cy - y)
            if sh > max_shift:
                max_shift = sh
            out += pack(code, _clamp(cx), _clamp(cy))
            n_out += 1
            px, py, pc = x, y, (cx, cy)
        else:
            if code == pjob.MAKELAYER:
                z = struct.unpack("<i", body[:4])[0] / 1000
                pc = tf(px, py, z)
            out += data[pos:pos + 2 + len(body)]
    return bytes(out), {"applied": True, "vectors_in": n_in, "vectors_out": n_out, "max_shift_mm": round(max_shift, 3)}
