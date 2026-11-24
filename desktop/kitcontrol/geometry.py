"""Netze für die 3D-Ansicht auf der Grafikkarte (Qt Quick 3D).

MeshGeometry: ein Bauteilnetz in Originalkoordinaten; Lage, Drehung und Skalierung setzt das Model in QML.
Kopien desselben Teils teilen sich eine Geometrie (gleicher Schlüssel). LineGeometry: Linien (Raster, Körbe).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Property, QByteArray, Signal
from PySide6.QtGui import QVector3D
from PySide6.QtQml import QmlElement
from PySide6.QtQuick3D import QQuick3DGeometry

QML_IMPORT_NAME = "KitControl"
QML_IMPORT_MAJOR_VERSION = 1

_MESHES: dict[str, np.ndarray] = {}     # Schlüssel -> Dreiecke (n, 3, 3), schon auf Anzeigegröße vereinfacht
MAX_TRIS = 400_000


def register(key: str, tris: np.ndarray) -> None:
    if key not in _MESHES:
        if len(tris) > MAX_TRIS:
            from kitslice.scene import simplify_mesh
            tris = simplify_mesh(tris, MAX_TRIS)
        _MESHES[key] = np.ascontiguousarray(tris, dtype=np.float32)


@QmlElement
class MeshGeometry(QQuick3DGeometry):
    keyChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._key = ""

    def _get_key(self):
        return self._key

    def _set_key(self, k):
        if k == self._key:
            return
        self._key = k
        self._build()
        self.keyChanged.emit()

    key = Property(str, _get_key, _set_key, notify=keyChanged)

    def _build(self):
        self.clear()
        t = _MESHES.get(self._key)
        if t is None or not len(t):
            self.update()
            return
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        n = (n / np.maximum(ln, 1e-12)).astype(np.float32)
        v = np.empty((len(t), 3, 6), dtype=np.float32)    # je Ecke: Position, Normale (flach schattiert)
        v[:, :, :3] = t
        v[:, :, 3:] = n[:, None, :]
        self.setVertexData(QByteArray(v.tobytes()))
        self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(QQuick3DGeometry.Attribute.PositionSemantic, 0, QQuick3DGeometry.Attribute.F32Type)
        self.addAttribute(QQuick3DGeometry.Attribute.NormalSemantic, 12, QQuick3DGeometry.Attribute.F32Type)
        lo, hi = t.reshape(-1, 3).min(axis=0), t.reshape(-1, 3).max(axis=0)
        self.setBounds(QVector3D(*map(float, lo)), QVector3D(*map(float, hi)))
        self.update()


@QmlElement
class LineGeometry(QQuick3DGeometry):
    segmentsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seg = []

    def _get(self):
        return self._seg

    def _set(self, s):
        self._seg = list(s or [])
        self.clear()
        a = np.asarray(self._seg, dtype=np.float32).reshape(-1, 3)
        if len(a) >= 2:
            self.setVertexData(QByteArray(a.tobytes()))
            self.setStride(12)
            self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Lines)
            self.addAttribute(QQuick3DGeometry.Attribute.PositionSemantic, 0, QQuick3DGeometry.Attribute.F32Type)
            self.setBounds(QVector3D(*map(float, a.min(axis=0))), QVector3D(*map(float, a.max(axis=0))))
        self.update()
        self.segmentsChanged.emit()

    segments = Property("QVariantList", _get, _set, notify=segmentsChanged)
