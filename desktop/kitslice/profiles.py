"""Pulverprofile: Slicer-Parameter (wie Central „Print Parameters“) plus Maschinenwerte für den Kit.

Vorlagen aus Central 1.2.0 (KitPA12CB_Z100, KitTPE_Z100, Materialtemperaturen) sind schreibgeschützt;
eigene Profile werden als JSON gespeichert und lassen sich exportieren/importieren und zum Pi mitschicken.
"""
from __future__ import annotations

import json
import os
import re
import sys

# Felder: (Typ, min, max) – Grenzen wie in Central bzw. kitctl.protocol
FIELDS = {
    "layer_um": (int, 50, 300),
    "perimeters": (int, 0, 5),
    "perimeter_offset_um": (int, 0, 1000),
    "hatch_offset_um": (int, 0, 2000),
    "hatch_spacing_um": (int, 20, 1000),
    "min_vector_um": (int, 0, 200),
}
TEMPS = {"surface_warmup": 180.0, "chamber_warmup": 150.0, "surface_print": 180.0, "chamber_print": 150.0}
LASER = (1.0, 1000.0)

BUILTIN = {
    "pa12": {
        "id": "pa12", "name": "Sintratec PA12", "builtin": True,
        "layer_um": 100, "perimeters": 1, "perimeter_offset_um": 200, "draw_original_boundary": False,
        "hatch_offset_um": 250, "hatch_spacing_um": 120, "hatch_angles_deg": [45, -45, -135, 135],
        "alternating_hatch": True, "min_vector_um": 25,
        "temps": {"surface_warmup": 150, "chamber_warmup": 140, "surface_print": 170, "chamber_print": 140},
        "laser_speed_mm_s": None, "contour_speed_mm_s": None, "lamps": None,
        "price_eur_kg": 96.0, "bulk_g_ml": 0.6, "part_g_cm3": 0.95,
    },
    "tpe": {
        "id": "tpe", "name": "Sintratec TPE", "builtin": True,
        "layer_um": 100, "perimeters": 1, "perimeter_offset_um": 250, "draw_original_boundary": False,
        "hatch_offset_um": 250, "hatch_spacing_um": 80, "hatch_angles_deg": [45, -45, -135, 135],
        "alternating_hatch": True, "min_vector_um": 25,
        "temps": {"surface_warmup": 90, "chamber_warmup": 40, "surface_print": 96, "chamber_print": 40},
        "laser_speed_mm_s": None, "contour_speed_mm_s": None, "lamps": None,
        "price_eur_kg": None, "bulk_g_ml": 0.6, "part_g_cm3": 0.95,
    },
}


def profile_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "KitControl", "profiles")
    else:
        d = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kitcontrol", "profiles")
    return os.environ.get("KIT_PROFILE_DIR", d)


def validate(p: dict) -> dict:
    """Prüft und normalisiert ein Profil. Wirft ValueError mit verständlicher Meldung."""
    if not str(p.get("name", "")).strip():
        raise ValueError("Profil braucht einen Namen")
    q = dict(p)
    for k, (typ, lo, hi) in FIELDS.items():
        if k not in q:
            raise ValueError(f"{k} fehlt")
        v = typ(q[k])
        if not lo <= v <= hi:
            raise ValueError(f"{k}: {lo}–{hi} erlaubt")
        q[k] = v
    ang = q.get("hatch_angles_deg") or [45, -45, -135, 135]
    q["hatch_angles_deg"] = [float(a) for a in ang][:16]
    t = q.get("temps")
    if t is not None:
        q["temps"] = {}
        for k, lim in TEMPS.items():
            v = float(t[k])
            if not 0 <= v <= lim:
                raise ValueError(f"Temperatur {k}: 0–{lim:g} °C")
            q["temps"][k] = v
    for k in ("laser_speed_mm_s", "contour_speed_mm_s"):
        if q.get(k) is not None:
            v = float(q[k])
            if not LASER[0] <= v <= LASER[1]:
                raise ValueError(f"Lasergeschwindigkeit {LASER[0]:g}–{LASER[1]:g} mm/s")
            q[k] = v
    if q.get("lamps") is not None:
        q["lamps"] = {w: float(q["lamps"][w]) for w in ("left", "right", "front")}
        if not all(0 <= v <= 100 for v in q["lamps"].values()):
            raise ValueError("Heizstrahler 0–100 %")
    # Erweiterte Strategien (fehlen = Verhalten von Central)
    q["contour_first"] = bool(q.get("contour_first", True))
    q["optimize_path"] = bool(q.get("optimize_path", False))
    q["keep_thin"] = bool(q.get("keep_thin", True))
    st = q.get("hatch_angle_step_deg")
    q["hatch_angle_step_deg"] = None if st in (None, "", 0) else float(st)
    if q["hatch_angle_step_deg"] is not None and not 1 <= abs(q["hatch_angle_step_deg"]) <= 179:
        raise ValueError("Winkelschritt 1–179°")
    q["island_mm"] = float(q.get("island_mm") or 0)
    if q["island_mm"] and not 2 <= q["island_mm"] <= 50:
        raise ValueError("Schachbrettfelder 2–50 mm (0 = aus)")
    q["skin_layers"] = int(q.get("skin_layers") or 0)
    if not 0 <= q["skin_layers"] <= 20:
        raise ValueError("Hautschichten 0–20")
    cs = q.get("core_spacing_um")
    q["core_spacing_um"] = None if cs in (None, "", 0) else int(cs)
    if q["core_spacing_um"] is not None and not q["hatch_spacing_um"] <= q["core_spacing_um"] <= 1000:
        raise ValueError("Kern-Schraffurabstand muss ≥ Schraffur-Abstand und ≤ 1000 µm sein")
    sh = q.get("shrink_pct") or {}
    q["shrink_pct"] = {a: float(sh.get(a, 0) or 0) for a in "xyz"}
    if not all(-5 <= v <= 5 for v in q["shrink_pct"].values()):
        raise ValueError("Schwundausgleich höchstens ±5 %")
    # Material und Kosten (für Pulverbedarf und Preis)
    for k, lo, hi in (("price_eur_kg", 0.0, 10000.0), ("bulk_g_ml", 0.05, 3.0), ("part_g_cm3", 0.05, 3.0)):
        v = q.get(k)
        q[k] = None if v in (None, "") else float(v)
        if q[k] is not None and not lo <= q[k] <= hi:
            raise ValueError(f"{k}: {lo:g}–{hi:g} erlaubt")
    q["draw_original_boundary"] = bool(q.get("draw_original_boundary", False))
    q["alternating_hatch"] = bool(q.get("alternating_hatch", True))
    return q


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profil"
    return s[:40]


def listing() -> list[dict]:
    out = [dict(v) for v in BUILTIN.values()]
    d = profile_dir()
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(d, fn), encoding="utf-8") as f:
                        p = validate(json.load(f))
                    p["builtin"] = False
                    p["id"] = fn[:-5]
                    out.append(p)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
    return out


def get(pid: str) -> dict:
    for p in listing():
        if p["id"] == pid:
            return p
    raise KeyError(f"Profil {pid!r} nicht gefunden")


def derive(base_id: str, name: str) -> dict:
    """Neues eigenes Profil auf Basis eines vorhandenen (noch nicht gespeichert)."""
    p = dict(get(base_id))
    p.update(name=name, builtin=False, base=base_id, id=None)
    return p


def save(p: dict) -> dict:
    q = validate(p)
    if q.get("builtin"):
        raise ValueError("Vorlagen sind schreibgeschützt – bitte als eigenes Profil speichern")
    d = profile_dir()
    os.makedirs(d, exist_ok=True)
    pid = q.get("id") or _slug(q["name"])
    if not q.get("id"):
        base, k = pid, 1
        while pid in BUILTIN or os.path.exists(os.path.join(d, pid + ".json")):
            k += 1
            pid = f"{base}-{k}"
    q["id"] = pid
    q["builtin"] = False
    tmp = os.path.join(d, pid + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, pid + ".json"))
    return q


def delete(pid: str) -> None:
    if pid in BUILTIN:
        raise ValueError("Vorlagen lassen sich nicht löschen")
    os.remove(os.path.join(profile_dir(), pid + ".json"))


def export(pid: str, path: str) -> None:
    p = get(pid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in p.items() if k not in ("id", "builtin")}, f, indent=2, ensure_ascii=False)


def import_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    p.pop("id", None)
    p["builtin"] = False
    return save(p)
