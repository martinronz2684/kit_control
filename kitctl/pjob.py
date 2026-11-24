"""Druckjob-Datei des Kits (pjob*.bin), wie Central sie in PrintJobKit.writeOut erzeugt.

Aufbau:
  512 Byte Kopf (Nullen)
  danach eine Folge von Kit-Befehlen, jeweils Code (uint16 LE) + Nutzdaten:
    27 MakeLayer   z (int32 µm) + Schichtnummer (int32)   – Beginn einer Schicht
    72 GosInfill   –                                      – folgende Vektoren sind Füllung
    73 GosContour  –                                      – folgende Vektoren sind Kontur
     1 Go          x, y (int32 µm)                        – Laser an, Linie zum Punkt
     2 Jump        x, y (int32 µm)                        – Laser aus, Sprung zum Punkt
Leere Schichten (PrintJobKit.writeOut): bis zu getMaxNumEmptyLayers() (20) leere Schichten am Stück
schreibt Central als MakeLayer ohne Vektoren; längere Lücken werden übersprungen. Z ist immer
(Nummer der geschriebenen Schicht + 1) * Schichtdicke, die Schichtnummer zählt ab 0.
Koordinaten: mm * 1000, Bauraum um den Ursprung zentriert (Central clippt auf ±55 mm).
"""
from __future__ import annotations

import struct

HEADER = 512
GO, JUMP, MAKELAYER, INFILL, CONTOUR = 1, 2, 27, 72, 73
_SIZE = {GO: 8, JUMP: 8, MAKELAYER: 8, INFILL: 0, CONTOUR: 0}


class JobFormatError(ValueError):
    pass


def _records(data: bytes, start: int = HEADER, end: int | None = None):
    end = len(data) if end is None else end
    i = start
    while i + 2 <= end:
        c = data[i] | data[i + 1] << 8
        n = _SIZE.get(c)
        if n is None:
            if not any(data[i:end]):   # Auffüllung am Dateiende
                return
            raise JobFormatError(f"unbekannter Befehl {c} bei Byte {i}")
        if i + 2 + n > end:
            raise JobFormatError("Datei endet mitten in einem Befehl")
        yield i, c, data[i + 2:i + 2 + n]
        i += 2 + n


def index(data: bytes) -> dict:
    """Schichten, Bauhöhe und Ausdehnung – für die Jobliste. Offsets erlauben schnellen Zugriff je Schicht."""
    if len(data) <= HEADER:
        raise JobFormatError("Datei zu kurz")
    offsets, zs = [], []
    xmin = ymin = 1e9
    xmax = ymax = -1e9
    vectors = 0
    for pos, c, body in _records(data):
        if c == MAKELAYER:
            z, _n = struct.unpack("<ii", body)
            offsets.append(pos)
            zs.append(z)
        elif c in (GO, JUMP):
            x, y = struct.unpack("<ii", body)
            if c == GO:
                vectors += 1
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
    if not offsets:
        raise JobFormatError("keine Schichten gefunden")
    steps = [b - a for a, b in zip(zs, zs[1:]) if b > a]
    # Kleinster Abstand (inkl. erster Schicht über 0); auf 5 µm runden, Central rechnet mit float
    layer_um = max(5, round(min([zs[0]] + steps) / 5) * 5)
    return {
        "layers": len(offsets),
        "layer_mm": round(layer_um / 1000, 3),
        "height_mm": round(zs[-1] / 1000, 2),
        "z_um": zs,
        "offsets": offsets,
        "vectors": vectors,
        "bbox": [round(v / 1000, 2) for v in (xmin, ymin, xmax, ymax)] if vectors else [0, 0, 0, 0],
    }


def layer(data: bytes, idx: dict, n: int, max_segments: int = 6000) -> dict:
    """Linien der Schicht n (1-basiert) in mm: Kontur vollständig, Füllung bei Bedarf ausgedünnt."""
    offs = idx["offsets"]
    n = max(1, min(len(offs), int(n)))
    start = offs[n - 1]
    end = offs[n] if n < len(offs) else len(data)
    contour, infill = [], []
    fam = INFILL
    px = py = 0
    for _pos, c, body in _records(data, start, end):
        if c in (INFILL, CONTOUR):
            fam = c
        elif c in (GO, JUMP):
            x, y = struct.unpack("<ii", body)
            if c == GO:
                (contour if fam == CONTOUR else infill).append((px, py, x, y))
            px, py = x, y
    budget = max(0, max_segments - len(contour))
    step = max(1, -(-len(infill) // budget)) if budget else len(infill) + 1
    flat = lambda segs: [round(v / 1000, 2) for s in segs for v in s]
    return {"layer": n, "z_mm": idx["z_um"][n - 1] / 1000, "contour": flat(contour),
            "infill": flat(infill[::step]) if budget else [], "thinned": step > 1}


# -- Erzeugen ---------------------------------------------------------------------
def build_central(layers, layer_mm: float, max_empty: int = 20) -> bytes:
    """Wie PrintJobKit.writeOut. layers: je Schicht (Konturen, Schraffur); Konturen sind geschlossene
    Polygone [(x, y), ...] in mm, Schraffur Strecken (x0, y0, x1, y1). Konturen vor Füllung."""
    um = lambda v: int(round(v * 1000))
    out = bytearray(HEADER)
    written = empty = 0
    for contours, hatches in layers:
        if not contours and not hatches:
            empty += 1
            if empty > max_empty:
                continue
        else:
            empty = 0
        out += struct.pack("<Hii", MAKELAYER, um((written + 1) * layer_mm), written)
        written += 1
        if contours:
            out += struct.pack("<H", CONTOUR)
            for poly in contours:
                out += struct.pack("<Hii", JUMP, um(poly[0][0]), um(poly[0][1]))
                for x, y in list(poly[1:]) + [poly[0]]:
                    out += struct.pack("<Hii", GO, um(x), um(y))
        if hatches:
            out += struct.pack("<H", INFILL)
            for x0, y0, x1, y1 in hatches:
                out += struct.pack("<HiiHii", JUMP, um(x0), um(y0), GO, um(x1), um(y1))
    return bytes(out)


# -- Demo-Job und Tests -------------------------------------------------------------
def build(layers: list[list[tuple[str, list[tuple[float, float]]]]], layer_mm: float = 0.1) -> bytes:
    """layers: je Schicht eine Liste (Art 'contour'/'infill', Polylinie in mm)."""
    um = lambda v: int(round(v * 1000))
    out = bytearray(HEADER)
    nr = 0
    for i, paths in enumerate(layers):
        if not paths:
            continue
        out += struct.pack("<Hii", MAKELAYER, um((i + 1) * layer_mm), nr)
        nr += 1
        fam = None
        for kind, pts in paths:
            f = CONTOUR if kind == "contour" else INFILL
            if f != fam:
                out += struct.pack("<H", f)
                fam = f
            out += struct.pack("<Hii", JUMP, um(pts[0][0]), um(pts[0][1]))
            for x, y in pts[1:]:
                out += struct.pack("<Hii", GO, um(x), um(y))
    return bytes(out)


def demo_job() -> bytes:
    """Beispieljob: Gehäuse mit Bohrung, Steg und Zapfen – 40 mm hoch bei 0,1 mm."""
    import math

    def rect(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

    def circle(cx, cy, r, n=48):
        return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]

    def hatch(x0, y0, x1, y1, gap=1.0, hole=None):
        paths, y, flip = [], y0 + gap / 2, False
        while y < y1:
            spans = [(x0, x1)]
            if hole:
                cx, cy, r = hole
                if abs(y - cy) < r:
                    d = math.sqrt(r * r - (y - cy) ** 2)
                    spans = [(x0, cx - d), (cx + d, x1)]
            for a, b in spans:
                if b - a > 0.3:
                    paths.append(("infill", [(b, y), (a, y)] if flip else [(a, y), (b, y)]))
            y += gap
            flip = not flip
        return paths

    layers = []
    for i in range(400):
        z = (i + 1) * 0.1
        p: list = []
        # Gehäuse 50×34 mm mit Bohrung Ø 14
        p += [("contour", rect(20, 20, 70, 54)), ("contour", circle(45, 37, 7))]
        p += hatch(20, 20, 70, 54, hole=(45, 37, 7))
        if z <= 25:      # Steg
            p += [("contour", rect(78, 22, 96, 52))] + hatch(78, 22, 96, 52)
        if 10 <= z <= 32:  # Zapfen
            p += [("contour", circle(36, 76, 8))]
            y = 68.5
            while y < 84:
                d = math.sqrt(max(0.0, 64 - (y - 76) ** 2))
                if d > 0.3:
                    p.append(("infill", [(36 - d, y), (36 + d, y)]))
                y += 1.0
        layers.append(p)
    return build(layers, 0.1)
