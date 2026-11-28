"""Laserkorrektur am Pi: gespeichert in <STATE_DIR>/compensation.json, angewendet beim Übertragen eines Jobs.

Die Werte kommen aus der Scan-Auswertung in Kit Control (POST /api/compensation, nur gekoppelte Geräte)
und gelten für jeden Job, den der Pi zum Kit schickt. Drucke, die Central direkt startet, laufen unverändert.
Umrechnung: kitctl/compensate.py.
"""
from __future__ import annotations

import json
import os
import threading
import time

from kitctl import compensate

_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": None}


def _file() -> str:
    return os.path.join(os.environ.get("KIT_STATE_DIR", "/var/lib/kitd"), "compensation.json")


def load() -> dict:
    f = _file()
    with _lock:
        try:
            mt = os.path.getmtime(f)
        except OSError:
            mt = None
        if mt is not None and mt == _cache["mtime"] and _cache["data"] is not None:
            out = json.loads(json.dumps(_cache["data"]))
            return _decorate(out)
        data = dict(compensate.ZERO)
        if mt is not None:
            try:
                with open(f) as fh:
                    data = compensate.validate(json.load(fh))
            except (OSError, ValueError, TypeError) as e:
                print(f"Laserkorrektur: Datei unbrauchbar ({e}) – Korrektur aus", flush=True)
                data = dict(compensate.ZERO)
        _cache.update(mtime=mt, data=data)
        out = json.loads(json.dumps(data))
    return _decorate(out)


def _decorate(out: dict) -> dict:
    out["active"] = compensate.active(out)
    g = out.get("grid")
    out["grid_max_um"] = round(max((abs(complex(a, b)) for ra, rb in zip(g["dx"], g["dy"]) for a, b in zip(ra, rb)),
                                   default=0.0) * 1000, 1) if g else 0.0
    return out


def _write(data: dict) -> dict:
    data = compensate.validate(data)
    data["updated"] = time.time()
    f = _file()
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with _lock:
        tmp = f + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, f)
        _cache.update(mtime=None, data=None)
    return load()


def save(data: dict) -> dict:
    return _write(data)


def reset() -> dict:
    return _write(dict(compensate.ZERO))


def set_enabled(on: bool) -> dict:
    d = load()
    d["enabled"] = bool(on)
    d.pop("active", None)
    d.pop("grid_max_um", None)
    return _write(d)


def active(c: dict | None) -> bool:
    return compensate.active(c)


def apply(data: bytes) -> tuple[bytes, dict]:
    return compensate.apply(data, load())
