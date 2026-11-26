"""Vom Bauraum zur Druckdatei: Szene + Pulverprofil -> pjob-Bytes (Format von Central/Kit)."""
from __future__ import annotations

import time

import numpy as np

from kitctl import pjob
from kitslice.scene import Scene
from kitslice.slicer import SliceSettings, slice_scene


def make_job(scene: Scene, profile: dict, progress=None, cancel=None):
    """Liefert (Bytes, Metadaten, Schichten). Wirft ValueError bei Problemen im Bauraum."""
    probs = scene.problems()
    if probs:
        raise ValueError("; ".join(probs))
    s = SliceSettings.from_profile(profile)
    t0 = time.time()
    layers = slice_scene(scene, s, progress, cancel)
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


def estimate_seconds(meta: dict, laser_mm_s: float, recoat_s: float = 30.0, jump_mm_s: float = 2000.0,
                     factor: float = 1.0, scan_k: float = 1.0) -> float:
    """Geschätzte Druckzeit ohne Aufheizen: Belichtung + Leerfahrten + je Schicht Beschichten und Aufwärmen.
    recoat_s und scan_k werden aus den gemessenen Schichtzeiten echter Drucke gelernt."""
    laser_mm_s = max(1.0, float(laser_mm_s))
    t = scan_k * meta.get("est_scan_m", 0) * 1000 / laser_mm_s + meta.get("est_jump_m", 0) * 1000 / jump_mm_s \
        + meta.get("layers", 0) * recoat_s
    return t * factor


def fit_layer_times(prints: list, jump_mm_s: float = 2000.0) -> dict | None:
    """Aus gemessenen Schichtzeiten (kitd /api/printlog) die feste Zeit je Schicht (Beschichten +
    Aufwärmen) und den Faktor auf die reine Laserzeit bestimmen: Dauer = a + k · Laserweg/v + Leerweg/vs."""
    xs, ys = [], []
    for p in prints or []:
        for row in p.get("rows", []):
            try:
                _, dur, scan, jump, v = row
            except (TypeError, ValueError):
                continue
            if dur is None or scan is None or not v or dur <= 0.5:
                continue
            xs.append(float(scan) / float(v))
            ys.append(float(dur) - float(jump or 0) / jump_mm_s)
    if len(ys) < 20:
        return None
    x, y = np.asarray(xs), np.asarray(ys)
    med = float(np.median(y))
    keep = (y > 0) & (y < max(5 * med, med + 60))          # Pausen, Fehler, Türöffnen nicht mitzählen
    x, y = x[keep], y[keep]
    if len(y) < 20:
        return None
    k, a = 1.0, float(np.median(y - x))
    if np.ptp(x) > 2.0:                                     # genug unterschiedliche Schichten für beide Werte
        kk, aa = np.polyfit(x, y, 1)
        if 0.3 <= kk <= 5.0 and aa > 0:
            k, a = float(kk), float(aa)
        else:
            a = float(np.median(y - x))
    return {"recoat_s": round(min(600.0, max(1.0, a)), 1), "scan_k": round(k, 3), "samples": int(len(y)),
            "prints": len(prints)}


def _scan_length(layers) -> float:
    n = 0.0
    for l in layers:
        for c in l.contours:
            n += float(np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T).sum())
        if len(l.hatches):
            h = np.asarray(l.hatches)
            n += float(np.hypot(h[:, 2] - h[:, 0], h[:, 3] - h[:, 1]).sum())
    return n
