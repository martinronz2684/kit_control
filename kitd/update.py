"""Software-Update aus GitHub, ausgelöst über die Oberfläche.

Das eigentliche Update läuft als eigener systemd-Dienst (kit-update.service),
damit es den Neustart von kitd und der App überlebt.
"""
from __future__ import annotations

import os
import subprocess
import time

DEMO = os.environ.get("KIT_DEMO") == "1"
VERSION_FILE = "/etc/kit/version"
_cache = {"latest": None, "checked": 0.0, "error": ""}
_demo = {"started": 0.0}


def _run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def current() -> str:
    try:
        return open(VERSION_FILE).read().strip() or "unbekannt"
    except OSError:
        return "unbekannt"


def running() -> bool:
    if DEMO:
        return 0 < time.time() - _demo["started"] < 12
    try:
        return _run(["systemctl", "is-active", "kit-update.service"], 5).stdout.strip() in ("activating", "active", "reloading")
    except Exception:
        return False


def log_tail(n=6) -> list[str]:
    if DEMO:
        steps = ["Lade martinronz2684/kit_control (main)", "== Pakete", "== Programm nach /opt/kit-controller", "== Dienste", "Version f00ba12 installiert."]
        k = int((time.time() - _demo["started"]) / 2.5) + 1 if _demo["started"] else 0
        return steps[:k]
    try:
        out = _run(["journalctl", "-u", "kit-update.service", "-n", str(n), "--no-pager", "-o", "cat"], 10).stdout
        return [l for l in out.splitlines() if l.strip()][-n:]
    except Exception:
        return []


def status() -> dict:
    cur = "da23149" if DEMO and not _demo["started"] else ("f00ba12" if DEMO else current())
    latest = _cache["latest"]
    return {"current": cur, "latest": latest, "checked": _cache["checked"], "error": _cache["error"],
            "available": bool(latest and cur not in ("unbekannt",) and latest != cur),
            "running": running(), "log": log_tail()}


def check() -> dict:
    if DEMO:
        _cache.update(latest="f00ba12", checked=time.time(), error="")
        return status()
    try:
        r = _run(["sudo", "-n", "/usr/local/sbin/kit-update", "--check"], 30)
        sha = r.stdout.strip()
        if r.returncode != 0 or not sha:
            raise RuntimeError((r.stderr.strip().splitlines() or ["keine Antwort"])[-1])
        _cache.update(latest=sha[:7], checked=time.time(), error="")
    except Exception as e:
        _cache.update(checked=time.time(), error=f"Prüfen fehlgeschlagen: {e}")
    return status()


def start() -> None:
    if running():
        return
    if DEMO:
        _demo["started"] = time.time()
        return
    r = _run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "kit-update.service"], 15)
    if r.returncode != 0:
        raise ValueError("Update konnte nicht gestartet werden: " + (r.stderr.strip() or "unbekannter Fehler"))
