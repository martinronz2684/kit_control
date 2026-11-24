"""Job-Bibliothek: Druckjobs von Central (und der Demo-Job) liegen auf dem Pi und lassen sich hier starten.

/var/lib/kitd/jobs/<id>.bin   die Datei, wie Central sie zum Kit schickt
/var/lib/kitd/jobs/<id>.json  Name, Herkunft, Datum, Schichten, Bauhöhe, Schicht-Offsets
/var/lib/kitd/jobs.json       Einstellungen (Autostart)
"""
from __future__ import annotations

import json
import os
import threading
import time

from kitctl import pjob

STATE_DIR = os.environ.get("KIT_STATE_DIR", "/var/lib/kitd")
MAX_JOBS = int(os.environ.get("KIT_MAX_JOBS", "30"))
_lock = threading.Lock()
_cache: dict = {}     # id -> (bytes, index) für die Vorschau


def _dir() -> str:
    d = os.path.join(STATE_DIR, "jobs")
    os.makedirs(d, exist_ok=True)
    return d


def _settings_file() -> str:
    return os.path.join(STATE_DIR, "jobs.json")


def settings() -> dict:
    try:
        with open(_settings_file()) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"autostart": bool(s.get("autostart", True))}


def set_autostart(on: bool) -> None:
    s = settings()
    s["autostart"] = bool(on)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_settings_file(), "w") as f:
        json.dump(s, f)


def _safe(job_id: str) -> str:
    if not job_id or not all(ch.isalnum() or ch in "-_" for ch in job_id):
        raise ValueError("ungültige Job-ID")
    return job_id


def save(data: bytes, source: str, name: str = "", background: bool = False, on_indexed=None) -> dict:
    """Job ablegen. Liefert die Metadaten (ohne Offsets). Ungültige Dateien werden trotzdem gespeichert,
    damit sie sich erneut starten lassen – nur ohne Vorschau.
    background: Datei sofort schreiben, Schichten im Hintergrund auswerten (die Brücke darf Central nicht warten lassen)."""
    idx, err = None, ""
    if not background:
        try:
            idx = pjob.index(data)
        except pjob.JobFormatError as e:
            err = str(e)
    now = time.time()
    job_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    with _lock:
        d = _dir()
        base = job_id
        k = 1
        while os.path.exists(os.path.join(d, job_id + ".bin")):
            k += 1
            job_id = f"{base}-{k}"
        meta = {
            "id": job_id,
            "name": name or ("Job von Central " if source == "central" else "Job ") + time.strftime("%d.%m. %H:%M", time.localtime(now)),
            "source": source,
            "created": now,
            "size": len(data),
            "error": err,
            "last_started": None,
            "starts": 0,
        }
        if idx:
            meta.update({k: idx[k] for k in ("layers", "layer_mm", "height_mm", "vectors", "bbox")})
        with open(os.path.join(d, job_id + ".bin"), "wb") as f:
            f.write(data)
        with open(os.path.join(d, job_id + ".json"), "w") as f:
            json.dump(meta, f)
        if idx:
            with open(os.path.join(d, job_id + ".idx"), "w") as f:
                json.dump({"offsets": idx["offsets"], "z_um": idx["z_um"]}, f)
        _prune(d)
    if background:
        threading.Thread(target=_index_later, args=(job_id, data, on_indexed), daemon=True).start()
    return meta


def _index_later(job_id: str, data: bytes, on_indexed) -> None:
    try:
        idx = pjob.index(data)
        with open(os.path.join(_dir(), job_id + ".idx"), "w") as f:
            json.dump({"offsets": idx["offsets"], "z_um": idx["z_um"]}, f)
        fields = {k: idx[k] for k in ("layers", "layer_mm", "height_mm", "vectors", "bbox")}
    except pjob.JobFormatError as e:
        fields = {"error": str(e)}
    except OSError:
        return
    try:
        update(job_id, **fields)
        if on_indexed:
            on_indexed(get(job_id))
    except ValueError:
        pass


def _prune(d: str) -> None:
    jobs = sorted((m for m in _metas(d)), key=lambda m: m["created"])
    for m in jobs[:-MAX_JOBS] if len(jobs) > MAX_JOBS else []:
        _remove(d, m["id"])


def _metas(d: str):
    for fn in os.listdir(d):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(d, fn)) as f:
                    yield json.load(f)
            except (OSError, ValueError):
                continue


def _remove(d: str, job_id: str) -> None:
    for ext in (".bin", ".json", ".idx"):
        try:
            os.remove(os.path.join(d, job_id + ext))
        except OSError:
            pass
    _cache.pop(job_id, None)


def listing() -> list[dict]:
    with _lock:
        return sorted(_metas(_dir()), key=lambda m: m["created"], reverse=True)


def get(job_id: str) -> dict:
    job_id = _safe(job_id)
    try:
        with open(os.path.join(_dir(), job_id + ".json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        raise ValueError("Job nicht gefunden")


def data(job_id: str) -> bytes:
    job_id = _safe(job_id)
    try:
        with open(os.path.join(_dir(), job_id + ".bin"), "rb") as f:
            return f.read()
    except OSError:
        raise ValueError("Job nicht gefunden")


def update(job_id: str, **kw) -> None:
    with _lock:
        m = get(job_id)
        m.update(kw)
        with open(os.path.join(_dir(), _safe(job_id) + ".json"), "w") as f:
            json.dump(m, f)


def delete(job_id: str) -> None:
    with _lock:
        _remove(_dir(), _safe(job_id))


def layer(job_id: str, n: int) -> dict:
    job_id = _safe(job_id)
    if job_id not in _cache:
        raw = data(job_id)
        try:
            with open(os.path.join(_dir(), job_id + ".idx")) as f:
                idx = json.load(f)
        except (OSError, ValueError):
            idx = pjob.index(raw)
        _cache.clear()          # nur einen Job im Speicher halten
        _cache[job_id] = (raw, idx)
    raw, idx = _cache[job_id]
    return pjob.layer(raw, idx, n)


def ensure_demo() -> None:
    """Im Demo-Modus einen Beispieljob anlegen, falls die Bibliothek leer ist."""
    if not listing():
        save(pjob.demo_job(), "demo", "Beispiel Gehäuse")
