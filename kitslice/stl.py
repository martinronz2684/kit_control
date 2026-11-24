"""STL lesen (binär und ASCII) und in ein indiziertes Netz umwandeln."""
from __future__ import annotations

import struct

import numpy as np


class STLError(ValueError):
    pass


def load(source) -> np.ndarray:
    """Dateipfad oder Bytes -> Dreiecke als Array (n, 3, 3) in mm."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
    else:
        with open(source, "rb") as f:
            data = f.read()
    if len(data) < 15:
        raise STLError("Datei zu kurz")
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            return _binary(data, n)
    if data.lstrip()[:5].lower() == b"solid":
        return _ascii(data)
    if len(data) >= 84:   # binär mit Rest am Ende
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n <= len(data):
            return _binary(data, n)
    raise STLError("keine gültige STL-Datei")


def _binary(data: bytes, n: int) -> np.ndarray:
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    arr = np.frombuffer(data, dtype=rec, count=n, offset=84)
    return _clean(arr["v"].astype(np.float64))


def _ascii(data: bytes) -> np.ndarray:
    vals = []
    for line in data.decode("ascii", "replace").splitlines():
        p = line.split()
        if len(p) == 4 and p[0].lower() == "vertex":
            try:
                vals.append((float(p[1]), float(p[2]), float(p[3])))
            except ValueError:
                raise STLError("ungültige Zahl in ASCII-STL") from None
    if not vals or len(vals) % 3:
        raise STLError("ASCII-STL ohne vollständige Dreiecke")
    return _clean(np.array(vals, dtype=np.float64).reshape(-1, 3, 3))


def _clean(tris: np.ndarray) -> np.ndarray:
    ok = np.isfinite(tris).all(axis=(1, 2))
    tris = tris[ok]
    # entartete Dreiecke (Fläche 0) weglassen
    a = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    tris = tris[np.einsum("ij,ij->i", a, a) > 1e-18]
    if len(tris) == 0:
        raise STLError("keine Dreiecke")
    return tris


def index(tris: np.ndarray, tol: float = 1e-5):
    """Dreiecksuppe -> (Eckpunkte (m, 3), Indizes (n, 3)). Gleiche Punkte (auf tol gerundet) werden zusammengelegt."""
    pts = tris.reshape(-1, 3)
    key = np.round(pts / tol).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    verts = np.zeros((len(uniq), 3))
    np.add.at(verts, inv.ravel(), pts)
    verts /= np.bincount(inv.ravel(), minlength=len(uniq))[:, None]
    faces = inv.reshape(-1, 3)
    good = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return verts, faces[good]


def save_binary(tris: np.ndarray, path: str) -> None:
    """Für Tests und Export: Dreiecke als binäre STL schreiben."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tris
    with open(path, "wb") as f:
        f.write(b"kitslice".ljust(80, b"\0") + struct.pack("<I", len(tris)) + rec.tobytes())
