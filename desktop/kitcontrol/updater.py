"""Update-Abfrage bei jedem Start: neueste Version vom GitHub-Release „desktop-setup“.

Das Release enthält KitControl-Setup.exe und version.txt (z. B. „1.0.42“). Ist das Repository privat,
liefert GitHub ohne Anmeldung 404 – dann gibt es still kein Update-Angebot.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.environ.get("KIT_UPDATE_REPO", "martinronz2684/kit_control")
BASE = f"https://github.com/{REPO}/releases/download/desktop-setup"


def _parse(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def check(current: str, timeout: float = 6.0) -> str | None:
    """Neuere Versionsnummer oder None."""
    try:
        with urllib.request.urlopen(BASE + "/version.txt", timeout=timeout) as r:
            latest = r.read(64).decode().strip()
    except Exception:
        return None
    return latest if _parse(latest) > _parse(current) else None


def download(progress=None) -> str:
    """Setup in den Temp-Ordner laden, Pfad zurück."""
    path = os.path.join(tempfile.gettempdir(), "KitControl-Setup.exe")
    with urllib.request.urlopen(BASE + "/KitControl-Setup.exe", timeout=30) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    return path


def run_setup(path: str) -> None:
    """Setup starten (ohne Rückfragen, mit Fortschrittsanzeige); die App beendet sich danach."""
    if sys.platform == "win32":
        subprocess.Popen([path, "/SILENT", "/SP-", "/NOCANCEL"], close_fds=True)
