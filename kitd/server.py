"""kitd – Hintergrunddienst zwischen Kit (USB) und Touch-Oberfläche (Browser).

    GET  /                 Oberfläche (ui/index.html)
    GET  /api/state        aktueller Zustand als JSON
    GET  /api/events       Server-Sent Events, ein Zustand pro Sekunde
    POST /api/cmd          {"cmd": "...", ...} -> {"ok": true} / {"ok": false, "error": "..."}

Nur Python-Standardbibliothek plus pyusb. KIT_DEMO=1 simuliert einen druckenden Kit.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kitctl import protocol as P
from kitctl.client import Kit

UI_DIR = Path(os.environ.get("KIT_UI_DIR", Path(__file__).resolve().parent.parent / "ui"))
PORT = int(os.environ.get("KIT_PORT", "8080"))
DEMO = os.environ.get("KIT_DEMO") == "1"
# Vorzeichen der Fahrbefehle: +1 heißt "positiver Wert = Plattform runter". Nach dem ersten Test anpassen.
MOVE_SIGN = float(os.environ.get("KIT_MOVE_SIGN", "1"))


class KitWorker(threading.Thread):
    """Owns the USB connection. Polls once per second, runs queued commands in between."""

    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.cmds: "queue.Queue[tuple[dict, queue.Queue]]" = queue.Queue()
        self.state = {"connected": False, "message": "Suche Kit …"}
        self.kit: Kit | None = None

    # -- state -----------------------------------------------------------------
    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)
            self.state["ts"] = time.time()

    # -- loop ------------------------------------------------------------------
    def run(self):
        while True:
            if self.kit is None:
                self._connect()
                if self.kit is None:
                    self._drain_cmds("Kein Kit verbunden")
                    time.sleep(3)
                    continue
            try:
                self._poll()
                self._run_cmds(deadline=time.time() + 1.0)
            except Exception as e:  # USB unplugged, timeout …
                self._set(connected=False, message=f"Verbindung verloren: {e}")
                try:
                    self.kit.close()
                except Exception:
                    pass
                self.kit = None
                time.sleep(2)

    def _connect(self):
        try:
            if DEMO:
                from kitd.demo import DemoTransport
                t = DemoTransport()
            else:
                from kitctl.client import UsbTransport
                t = UsbTransport()
            kit = Kit(t)
            ident = kit.connect()
            self.kit = kit
            self._set(connected=True, message="", model=ident.model_name, firmware=ident.firmware,
                      protocol=ident.comm, uid=ident.uid.hex(), demo=DEMO)
        except SystemExit as e:  # UsbTransport: no device
            self._set(connected=False, message=str(e))
        except Exception as e:
            self._set(connected=False, message=f"Verbindung fehlgeschlagen: {e}")

    def _poll(self):
        snap = self.kit.snapshot()
        out = {}
        st = snap["state"]
        if not isinstance(st, Exception):
            out.update(state=st.state, warning_code=st.warnings, error_code=st.errors,
                       waiting_for_sd=st.state == P.STATE_WAITING_FOR_SD_CARD)
        pr = snap["print"]
        if not isinstance(pr, Exception):
            out.update(printing=pr.printing, layer=pr.layer, elapsed_s=pr.elapsed_s, percent=pr.percent)
        for k in ("surface", "chamber"):
            v = snap[k]
            if not isinstance(v, Exception):
                out[k] = round(v.celsius, 1)
        lv = snap["live"]
        if not isinstance(lv, Exception):
            out.update(target_chamber_warmup=lv.chamber_warmup, target_surface_warmup=lv.surface_warmup,
                       target_chamber_print=lv.chamber_print, target_surface_print=lv.surface_print,
                       laser_speed=lv.laser_speed)
        cd = snap["countdown"]
        if not isinstance(cd, Exception):
            out.update(countdown_on=cd.enabled, countdown_s=cd.seconds)
        now = time.time()
        if now - getattr(self, "_frames_at", 0) > 5:
            self._frames_at = now
            from kitctl.codes import describe
            for key, name in (("errors", "errors"), ("warnings", "warnings")):
                try:
                    out[key] = [describe(c) for c in self.kit.request(name).codes]
                except P.ProtocolError as e:
                    snap[name] = e
        errs = [f"{k}: {v}" for k, v in snap.items() if isinstance(v, Exception)]
        out["message"] = "; ".join(errs)
        self._set(**out)

    # -- commands --------------------------------------------------------------
    def submit(self, cmd: dict, timeout=8.0) -> dict:
        reply: queue.Queue = queue.Queue()
        self.cmds.put((cmd, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": "Zeitüberschreitung"}

    def _drain_cmds(self, why: str):
        while not self.cmds.empty():
            _, reply = self.cmds.get_nowait()
            reply.put({"ok": False, "error": why})

    def _run_cmds(self, deadline: float):
        while time.time() < deadline:
            try:
                cmd, reply = self.cmds.get(timeout=max(0.0, deadline - time.time()))
            except queue.Empty:
                return
            try:
                self.kit.command(self._encode(cmd))
                reply.put({"ok": True})
            except (P.ProtocolError, ValueError, KeyError) as e:
                reply.put({"ok": False, "error": str(e)})

    def _encode(self, c: dict) -> bytes:
        name = c.get("cmd")
        printing = self.snapshot().get("printing", False)
        motion = {"move", "make_layer", "powder_prep_on"}
        if printing and name in motion:
            raise ValueError("Während des Drucks gesperrt")
        if name == "move":
            mm = float(c["mm"])
            if not 0 < abs(mm) <= 120:
                raise ValueError("Fahrweg muss zwischen 0,1 und 120 mm liegen")
            return P.cmd_move(c["platform"], MOVE_SIGN * mm, relative=True)
        if name == "make_layer":
            t = float(c["mm"])
            if not 0.05 <= t <= 0.3:
                raise ValueError("Schichtdicke 0,05–0,3 mm")
            return P.cmd_make_layer(t)
        if name == "lamp":
            return P.cmd_lamp(c["which"], float(c["percent"]))
        if name == "target":
            t = float(c["celsius"])
            if not 0 <= t <= 185:
                raise ValueError("Temperatur 0–185 °C")
            return P.cmd_target(c["which"], t)
        if name == "warmup":
            return P.cmd_warmup(bool(c["on"]))
        if name in P.SIMPLE:
            return P.cmd_simple(P.SIMPLE[name])
        raise ValueError(f"unbekannter Befehl {name!r}")


WORKER = KitWorker()


class Handler(BaseHTTPRequestHandler):
    server_version = "kitd/0.2"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/wifi"):
            from kitd import wifi
            return self._json(wifi.status(rescan="rescan=1" in self.path))
        if self.path == "/api/state":
            return self._json(WORKER.snapshot())
        if self.path == "/api/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b"data: " + json.dumps(WORKER.snapshot()).encode() + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                return
        path = "index.html" if self.path in ("/", "/index.html") else self.path.lstrip("/")
        f = (UI_DIR / path).resolve()
        if not f.is_relative_to(UI_DIR.resolve()) or not f.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css",
                 "png": "image/png", "svg": "image/svg+xml"}.get(f.suffix.lstrip("."), "application/octet-stream")
        data = f.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/cmd":
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if self.client_address[0] not in ("127.0.0.1", "::1") and os.environ.get("KIT_REMOTE") != "1":
            return self._json({"ok": False, "error": "Bedienung nur am Gerät"}, HTTPStatus.FORBIDDEN)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            cmd = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json({"ok": False, "error": "ungültige Anfrage"}, HTTPStatus.BAD_REQUEST)
        if cmd.get("cmd") in ("wifi_connect", "wifi_disconnect"):
            from kitd import wifi
            try:
                if cmd["cmd"] == "wifi_connect":
                    wifi.connect(str(cmd.get("ssid", "")), str(cmd.get("password", "")))
                else:
                    wifi.disconnect()
                return self._json({"ok": True})
            except ValueError as e:
                return self._json({"ok": False, "error": str(e)})
        if cmd.get("cmd") in ("reboot", "poweroff"):
            import subprocess
            subprocess.Popen(["sudo", "-n", "/usr/bin/systemctl", cmd["cmd"]])
            return self._json({"ok": True})
        self._json(WORKER.submit(cmd))


def main():
    WORKER.start()
    host = os.environ.get("KIT_HOST", "127.0.0.1")
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
