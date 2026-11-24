"""Vom Bauraum zur Druckdatei: Szene + Pulverprofil -> pjob-Bytes (Format von Central/Kit)."""
from __future__ import annotations

import time

import numpy as np

from kitctl import pjob
from kitslice.scene import Scene
from kitslice.slicer import SliceSettings, slice_mesh


def make_job(scene: Scene, profile: dict, progress=None, cancel=None):
    """Liefert (Bytes, Metadaten, Schichten). Wirft ValueError bei Problemen im Bauraum."""
    probs = scene.problems()
    if probs:
        raise ValueError("; ".join(probs))
    s = SliceSettings.from_profile(profile)
    t0 = time.time()
    layers = slice_mesh(None, s, progress, cancel, mesh=scene.indexed())
    idx = {}
    data = pjob.build_central([(l.contours, l.hatches, l.contour_first) for l in layers], s.layer_mm, info=idx)
    if progress:
        progress(1.0)
    meta = {
        "layers": idx["layers"], "layer_mm": idx["layer_mm"], "height_mm": idx["height_mm"],
        "vectors": idx["vectors"], "bbox": idx["bbox"], "profile": profile.get("name"),
        "parts": [p.name for p in scene.parts], "slice_s": round(time.time() - t0, 1),
        "est_scan_m": round(_scan_length(layers) / 1000, 1),
        "est_jump_m": round(_jump_length(layers) / 1000, 1),
        "index": {"offsets": idx["offsets"], "z_um": idx["z_um"]},
    }
    return data, meta, layers


def _jump_length(layers) -> float:
    """Leerfahrten des Lasers (vom Ende eines Vektors zum Anfang des nächsten)."""
    n = 0.0
    for l in layers:
        # Sprünge: zwischen Konturen und zwischen Schraffurstrecken
        if len(l.hatches):
            h = np.asarray(l.hatches)
            n += float(np.hypot(h[1:, 0] - h[:-1, 2], h[1:, 1] - h[:-1, 3]).sum())
        starts = [np.asarray(c)[0] for c in l.contours]
        for a, b in zip(starts[:-1], starts[1:]):
            n += float(np.hypot(*(b - a)))
    return n


def estimate_seconds(meta: dict, laser_mm_s: float, recoat_s: float = 10.0, jump_mm_s: float = 2000.0,
                     factor: float = 1.0) -> float:
    """Geschätzte Druckzeit ohne Aufheizen: Belichtung + Leerfahrten + Beschichten je Schicht.
    factor wird aus echten Drucken gelernt (gemessene / geschätzte Zeit)."""
    laser_mm_s = max(1.0, float(laser_mm_s))
    t = meta.get("est_scan_m", 0) * 1000 / laser_mm_s + meta.get("est_jump_m", 0) * 1000 / jump_mm_s \
        + meta.get("layers", 0) * recoat_s
    return t * factor


def _scan_length(layers) -> float:
    n = 0.0
    for l in layers:
        for c in l.contours:
            n += float(np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T).sum())
        if len(l.hatches):
            h = np.asarray(l.hatches)
            n += float(np.hypot(h[:, 2] - h[:, 0], h[:, 3] - h[:, 1]).sum())
    return n
