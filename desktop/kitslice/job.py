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
    layers = slice_mesh(scene.merged(), s, progress, cancel)
    data = pjob.build_central([(l.contours, l.hatches) for l in layers], s.layer_mm)
    if progress:
        progress(1.0)
    idx = pjob.index(data)
    meta = {
        "layers": idx["layers"], "layer_mm": idx["layer_mm"], "height_mm": idx["height_mm"],
        "vectors": idx["vectors"], "bbox": idx["bbox"], "profile": profile.get("name"),
        "parts": [p.name for p in scene.parts], "slice_s": round(time.time() - t0, 1),
        "est_scan_m": round(_scan_length(layers) / 1000, 1),
    }
    return data, meta, layers


def _scan_length(layers) -> float:
    n = 0.0
    for l in layers:
        for c in l.contours:
            n += float(np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T).sum())
        if l.hatches:
            h = np.asarray(l.hatches)
            n += float(np.hypot(h[:, 2] - h[:, 0], h[:, 3] - h[:, 1]).sum())
    return n
