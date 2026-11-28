"""Verbindung PC <-> Kit Control am Pi (eigene API, ohne USB-Umweg). Nur Standardbibliothek.

  Suche:     UDP-Broadcast "KITCONTROL-HTTP?" an Port 8767 -> "KITCONTROL-HTTP <port> <name>"
  Zustand:   GET  http://<pi>:8080/api/state            (einmalig)
             GET  http://<pi>:8080/api/events           (Server-Sent Events, jede Sekunde)
  Jobs:      GET  /api/jobs, GET /api/jobs/<id>/layer/<n>, DELETE /api/jobs/<id>
  Senden:    POST /api/jobs  Rumpf = Druckdatei, Kopfzeilen X-Job-Name, X-Job-Profile (JSON, base64),
             X-Job-Start: 1 = nach dem Übertragen gleich starten
  Kopplung:  GET /api/pair/hello, POST /api/pair/start, POST /api/pair/confirm (kitctl/auth.py);
             danach trägt jede Anfrage eine Unterschrift. Ohne Kopplung antwortet der Pi mit 401.
"""
from __future__ import annotations

import base64
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import kitslice  # noqa: F401  (Pfad zu kitctl)
from kitctl import auth as A

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


# Kopplung je Pi-Adresse: {"client_id", "key" (hex)} – setzt die App nach dem Abgleich über /api/pair/hello
AUTH: dict[str, dict] = {}
# Abweichung der Pi-Uhr von der eigenen (s), aus /api/pair/hello
OFFSET: dict[str, float] = {}


class NotPaired(Exception):
    """Der Pi kennt dieses Gerät nicht (HTTP 401) – erst koppeln."""

    def __init__(self, info: dict | None = None):
        super().__init__((info or {}).get("error", "Nicht gekoppelt"))
        self.info = info or {}


class PairFailed(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def set_auth(host: str, pairing: dict | None) -> None:
    if pairing and pairing.get("client_id") and pairing.get("key"):
        AUTH[host] = {"client_id": pairing["client_id"], "key": pairing["key"]}
    else:
        AUTH.pop(host, None)


class Pi:
    def __init__(self, host: str, port: int = HTTP_PORT, timeout: float = 10.0):
        self.host = host
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self._pair = None

    # -- Unterschrift -------------------------------------------------------
    def _auth_fields(self, method: str, path: str, body: bytes | None, headers: dict) -> dict | None:
        a = AUTH.get(self.host)
        if not a:
            return None
        ts = str(int(time.time() + OFFSET.get(self.host, 0.0)))
        nonce = A.new_nonce()
        sig = A.sign(bytes.fromhex(a["key"]), method, path, ts, nonce, A.body_hash(body), A.signed_headers(headers.get))
        return {"X-Kit-Client": a["client_id"], "X-Kit-Time": ts, "X-Kit-Nonce": nonce, "X-Kit-Sig": sig}

    def _request(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None):
        hdr = dict(headers or {})
        hdr.update(self._auth_fields(method, path, data, hdr) or {})
        return urllib.request.Request(self.base + path, data=data, headers=hdr, method=method)

    @staticmethod
    def _err_json(e: urllib.error.HTTPError) -> dict:
        try:
            j = json.loads(e.read())
            return j if isinstance(j, dict) else {"ok": False, "error": f"HTTP {e.code}"}
        except ValueError:
            return {"ok": False, "error": f"HTTP {e.code}"}

    def _call(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None,
              timeout: float | None = None, raise_401: bool = True) -> dict:
        try:
            with urllib.request.urlopen(self._request(method, path, data, headers), timeout=timeout or self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            j = self._err_json(e)
            if e.code == 401 and raise_401:
                raise NotPaired(j) from None
            return j

    def _get(self, path: str):
        return self._call("GET", path)

    # -- Kopplung -----------------------------------------------------------
    def hello(self) -> dict | None:
        """{"device_id", "name", "time", "paired"} – None bei älterer Pi-Software ohne Kopplung."""
        t0 = time.time()
        try:
            with urllib.request.urlopen(self._request("GET", "/api/pair/hello"), timeout=self.timeout) as r:
                j = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        t1 = time.time()
        if j.get("time"):
            OFFSET[self.host] = float(j["time"]) - (t0 + t1) / 2
        return j

    def pair_start(self, name: str, kind: str = "pc") -> dict:
        """Kopplung anfragen – am Display erscheint der Code. {"request_id", "expires_in", "device_id"}"""
        a, a_pub = A.keypair()
        body = json.dumps({"name": name, "kind": kind, "A": format(a_pub, "x")}).encode()
        r = self._call("POST", "/api/pair/start", body, {"Content-Type": "application/json"}, raise_401=False)
        if not r.get("ok"):
            raise PairFailed(r.get("error", "Kopplung nicht möglich"))
        self._pair = (a, a_pub, r)
        return r

    def pair_confirm(self, code: str) -> dict:
        """Code vom Display bestätigen. Liefert die Kopplung {"client_id", "key", "device_id"}."""
        if not self._pair:
            raise PairFailed("Keine Kopplung angefragt")
        code = "".join(ch for ch in str(code) if ch.isdigit())
        if len(code) != A.CODE_DIGITS:
            raise PairFailed(f"Der Code hat {A.CODE_DIGITS} Ziffern")
        a, a_pub, r = self._pair
        b_pub = int(r["B"], 16)
        key = A.derive(code, a_pub, b_pub, A.shared_secret(a, b_pub))
        body = json.dumps({"request_id": r["request_id"], "mac": A.mac(key, "client", r["request_id"])}).encode()
        try:
            with urllib.request.urlopen(self._request("POST", "/api/pair/confirm", body, {"Content-Type": "application/json"}),
                                        timeout=self.timeout) as resp:
                j = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            j = self._err_json(e)
            raise PairFailed(j.get("error", f"HTTP {e.code}"), e.code) from None
        if not j.get("ok"):
            raise PairFailed(j.get("error", "Kopplung fehlgeschlagen"))
        if A.mac(key, "server", j["client_id"]) != j.get("mac"):
            raise PairFailed("Der Kit hat sich nicht ausgewiesen – Kopplung verworfen")
        self._pair = None
        return {"client_id": j["client_id"], "key": key.hex(), "device_id": j.get("device_id", r.get("device_id", ""))}

    def state(self) -> dict:
        return self._get("/api/state")

    def printlog(self) -> dict:
        return self._get("/api/printlog")

    def jobs(self) -> dict:
        return self._get("/api/jobs")

    def layer(self, job_id: str, n: int) -> dict:
        return self._get(f"/api/jobs/{urllib.parse.quote(job_id)}/layer/{int(n)}")

    def delete_job(self, job_id: str) -> dict:
        return self._call("DELETE", f"/api/jobs/{urllib.parse.quote(job_id, safe='')}")

    def compensation(self) -> dict:
        return self._get("/api/compensation")

    def set_compensation(self, comp: dict) -> dict:
        return self._call("POST", "/api/compensation", json.dumps(comp).encode(), {"Content-Type": "application/json"})

    def events(self):
        """Zustände als Generator (blockiert; in einem eigenen Thread verwenden)."""
        try:
            r = urllib.request.urlopen(self._request("GET", "/api/events", headers={"Accept": "text/event-stream"}), timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise NotPaired(self._err_json(e)) from None
            raise
        with r:
            for line in r:
                if line.startswith(b"data: "):
                    yield json.loads(line[6:])

    def cmd(self, cmd: dict) -> dict:
        """Bedienbefehl (wie am Display). Erlaubt, wenn am Display „Bedienung vom PC“ an ist und kein Druck läuft."""
        return self._call("POST", "/api/cmd", json.dumps(cmd).encode(), {"Content-Type": "application/json"}, raise_401=False)

    def send_job(self, data: bytes, name: str, profile: dict | None = None, start: bool = False) -> dict:
        """Druckdatei zum Pi. start=True: gleich drucken, falls der Kit bereit ist.
        Antwort: {"ok", "job": {...}, "started": bool, "error"?}"""
        hdr = {"Content-Type": "application/octet-stream", "X-Job-Name": urllib.parse.quote(name[:80]),
               "X-Job-Start": "1" if start else "0"}
        if profile:
            hdr["X-Job-Profile"] = base64.b64encode(json.dumps(profile).encode()).decode()
        return self._call("POST", "/api/jobs", data, hdr, timeout=max(self.timeout, 60), raise_401=False)
