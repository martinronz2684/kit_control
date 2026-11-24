"""Verbindung PC <-> Kit Control am Pi (eigene API, ohne USB-Umweg). Nur Standardbibliothek.

  Suche:     UDP-Broadcast "KITCONTROL-HTTP?" an Port 8767 -> "KITCONTROL-HTTP <port> <name>"
  Zustand:   GET  http://<pi>:8080/api/state            (einmalig)
             GET  http://<pi>:8080/api/events           (Server-Sent Events, jede Sekunde)
  Jobs:      GET  /api/jobs, GET /api/jobs/<id>/layer/<n>
  Senden:    POST /api/jobs  Rumpf = Druckdatei, Kopfzeilen X-Job-Name, X-Job-Profile (JSON, base64),
             X-Job-Start: 1 = nach dem Übertragen gleich starten
"""
from __future__ import annotations

import base64
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

DISCOVERY_PORT = 8767
HTTP_PORT = 8080


def discover(timeout: float = 1.5) -> list[dict]:
    """Alle Kit-Control-Geräte im Netz: [{"host", "port", "name"}]."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.3)
    found = {}
    try:
        for target in ("255.255.255.255", "10.55.0.1"):   # WLAN/LAN und USB-Netz am Pi
            try:
                s.sendto(b"KITCONTROL-HTTP?", (target, DISCOVERY_PORT))
            except OSError:
                pass
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg, addr = s.recvfrom(256)
            except socket.timeout:
                continue
            p = msg.decode(errors="replace").split(None, 2)
            if len(p) >= 2 and p[0] == "KITCONTROL-HTTP":
                found[addr[0]] = {"host": addr[0], "port": int(p[1]), "name": p[2] if len(p) > 2 else addr[0]}
    finally:
        s.close()
    return list(found.values())


class Pi:
    def __init__(self, host: str, port: int = HTTP_PORT, timeout: float = 10.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return json.loads(r.read())

    def state(self) -> dict:
        return self._get("/api/state")

    def jobs(self) -> dict:
        return self._get("/api/jobs")

    def layer(self, job_id: str, n: int) -> dict:
        return self._get(f"/api/jobs/{urllib.parse.quote(job_id)}/layer/{int(n)}")

    def events(self):
        """Zustände als Generator (blockiert; in einem eigenen Thread verwenden)."""
        req = urllib.request.Request(self.base + "/api/events", headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(req, timeout=30) as r:
            for line in r:
                if line.startswith(b"data: "):
                    yield json.loads(line[6:])

    def cmd(self, cmd: dict) -> dict:
        """Bedienbefehl (wie am Display). Der Pi erlaubt das aus dem Netz nur mit KIT_REMOTE=1."""
        req = urllib.request.Request(self.base + "/api/cmd", data=json.dumps(cmd).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except ValueError:
                return {"ok": False, "error": f"HTTP {e.code}"}

    def send_job(self, data: bytes, name: str, profile: dict | None = None, start: bool = False) -> dict:
        """Druckdatei zum Pi. start=True: gleich drucken, falls der Kit bereit ist.
        Antwort: {"ok", "job": {...}, "started": bool, "error"?}"""
        hdr = {"Content-Type": "application/octet-stream", "X-Job-Name": urllib.parse.quote(name[:80]),
               "X-Job-Start": "1" if start else "0"}
        if profile:
            hdr["X-Job-Profile"] = base64.b64encode(json.dumps(profile).encode()).decode()
        req = urllib.request.Request(self.base + "/api/jobs", data=data, headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=max(self.timeout, 60)) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except ValueError:
                return {"ok": False, "error": f"HTTP {e.code}"}
