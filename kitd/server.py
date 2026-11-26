"""kitd – Hintergrunddienst zwischen Kit (USB) und Touch-Oberfläche (Browser).

    GET  /                 Oberfläche (ui/index.html)
    GET  /api/printlog     Schichtzeiten der letzten Drucke (für die Druckzeit-Schätzung in Kit Control)
    GET  /app              Handy-Oberfläche (ui/phone.html), auf dem iPhone „Zum Home-Bildschirm“
    GET  /api/state        aktueller Zustand als JSON
    GET  /api/events       Server-Sent Events, ein Zustand pro Sekunde
    POST /api/cmd          {"cmd": "...", ...} -> {"ok": true} / {"ok": false, "error": "..."}  (nur am Gerät)
    POST /api/jobs         Druckdatei von der PC-App (Kit Control Desktop), optional sofort starten
    DELETE /api/jobs/<id>  Job aus der Bibliothek löschen (PC-App; nicht während er übertragen wird)

Lesen (Zustand, Jobs, Schichtvorschau) geht aus dem Netz, damit die PC-App den Druck live verfolgen kann.
Bedienbefehle aus dem Netz: Schalter „Bedienung vom PC“ am Display (gemerkt in kitd.json, KIT_REMOTE=1 erzwingt ihn),
nie während eines Drucks – dann nur Abbrechen/Abkühlen. Jobs annehmen: KIT_NET_JOBS=0
schaltet es ab, KIT_NET_START=0 verbietet das Starten aus dem Netz.

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
# Oberfläche: mm > 0 = nach unten. Central: positiver Fahrweg = nach oben (PowderPaneControllerKit) -> umdrehen
MOVE_SIGN = float(os.environ.get("KIT_MOVE_SIGN", "-1"))


STATE_DIR = os.environ.get("KIT_STATE_DIR", "/var/lib/kitd")
NET_JOBS = os.environ.get("KIT_NET_JOBS", "1") == "1"
NET_START = os.environ.get("KIT_NET_START", "1") == "1"
# Nur am Gerät: Netzwerk, Updates, Neustart und der Schalter selbst
from kitd.printlog import PrintLog  # noqa: E402
PRINTLOG = PrintLog(STATE_DIR)

LOCAL_ONLY = {"pc_link", "update_check", "update_start", "wifi_connect", "wifi_disconnect", "demo",
              "remote_control", "job_autostart", "lamp_legacy"}
# Was der PC auch während eines Drucks darf: nur anhalten
STOP_CMDS = {"abort_print", "stop_sintering"}


def _cfg_file() -> str:
    return os.path.join(STATE_DIR, "kitd.json")


def _cfg() -> dict:
    try:
        with open(_cfg_file()) as f:
            c = json.load(f)
            return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def remote_enabled() -> bool:
    return os.environ.get("KIT_REMOTE") == "1" or bool(_cfg().get("remote_control", False))


def set_remote(on: bool) -> None:
    c = _cfg()
    c["remote_control"] = bool(on)
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _cfg_file() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, _cfg_file())


MAX_UPLOAD = int(os.environ.get("KIT_MAX_UPLOAD_MB", "1024")) * 1024 * 1024
IGNORED_WARNINGS = {int(x) for x in os.environ.get("KIT_IGNORE_WARNINGS", "81").replace(" ", "").split(",") if x}


class KitWorker(threading.Thread):
    """Owns the USB connection. Polls once per second, runs queued commands in between."""

    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.cmds: "queue.Queue[tuple[dict, queue.Queue]]" = queue.Queue()
        self.state = {"connected": False, "message": "Suche Kit …"}
        self.kit: Kit | None = None
        # Alle USB-Zugriffe laufen unter dieser Sperre (eigene Abfragen und Central über WLAN).
        self.usb = threading.RLock()
        # Demo-Modus: simulierter Kit statt USB. Umschaltbar unter System, gilt bis zum Neustart.
        self.demo = DEMO
        self.want_demo = DEMO

    # -- state -----------------------------------------------------------------
    def snapshot(self) -> dict:
        with self.lock:
            st = dict(self.state)
        st["remote_control"] = remote_enabled()
        return st

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)
            self.state["ts"] = time.time()

    # -- loop ------------------------------------------------------------------
    def run(self):
        while True:
            if self.want_demo != self.demo:
                self.demo = self.want_demo
                if self.kit is not None:
                    try:
                        self.kit.close()
                    except Exception:
                        pass
                    self.kit = None
                with self.lock:   # alte Werte verwerfen
                    self.state = {"connected": False, "message": "Demo startet …" if self.demo else "Suche Kit …"}
            if self.kit is None:
                self._connect()
                if self.kit is None:
                    self._drain_cmds("Kein Kit verbunden")
                    for _ in range(30):   # 3 s warten, aber auf Demo-Umschaltung sofort reagieren
                        if self.want_demo != self.demo:
                            break
                        time.sleep(0.1)
                    continue
            try:
                with self.usb:
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
            if self.demo:
                from kitd.demo import DemoTransport
                t = DemoTransport()
            else:
                from kitctl.client import UsbTransport
                t = UsbTransport()
            kit = Kit(t)
            try:
                ident = kit.connect()
            except Exception:
                t.close()   # Interface freigeben, sonst ist es beim nächsten Versuch „busy“
                raise
            self.kit = kit
            self._set(connected=True, message="", model=ident.model_name, firmware=ident.firmware,
                      protocol=ident.comm, uid=ident.uid.hex(), demo=self.demo)
            self._read_scaling(backup=True)
            self._set(lamps=self._lamps())
        except SystemExit as e:  # UsbTransport: no device
            self._set(connected=False, message=str(e))
        except Exception as e:
            self._set(connected=False, message=f"Verbindung fehlgeschlagen: {e}")

    LAMP_FILE = "heizstrahler.json"

    def _lamps(self) -> dict:
        try:
            with open(os.path.join(STATE_DIR, self.LAMP_FILE)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _remember_lamp(self, which: str, pct: float):
        """Die Firmware kann die Lampenleistung nicht zurückmelden – der Pi merkt sich, was er gesendet hat."""
        d = self._lamps()
        d[which] = round(pct)
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(os.path.join(STATE_DIR, self.LAMP_FILE), "w") as f:
                json.dump(d, f)
        except OSError:
            pass
        self._set(lamps=d)

    def _read_scaling(self, backup=False):
        """Scaling vom Kit lesen; beim ersten Verbinden je Kit die Werkswerte sichern."""
        try:
            with self.usb:
                sc = self.kit.request("scaling")
        except Exception as e:
            self._set(scaling=None, scaling_error=str(e))
            return
        pct = {k: round((getattr(sc, k) - 1) * 100, 2) for k in "xyz"}
        self._set(scaling=pct, scaling_error="")
        live = None
        try:
            with self.usb:
                lv = self.kit.request("live")
            live = {"surface_warmup": lv.surface_warmup, "chamber_warmup": lv.chamber_warmup,
                    "surface_print": lv.surface_print, "chamber_print": lv.chamber_print, "laser_speed": lv.laser_speed}
        except Exception:
            pass
        if backup:
            uid = self.snapshot().get("uid", "unbekannt")
            f = os.path.join(STATE_DIR, f"werkswerte-{'demo' if self.demo else uid}.json")
            try:
                if not os.path.exists(f):
                    os.makedirs(STATE_DIR, exist_ok=True)
                    with open(f, "w") as fh:
                        json.dump({"scaling": pct, "live": live, "saved": time.strftime("%Y-%m-%d %H:%M")}, fh)
                with open(f) as fh:
                    self._set(factory=json.load(fh))
            except OSError:
                pass

    def _poll(self):
        snap = self.kit.snapshot()
        out = {}
        st = snap["state"]
        if not isinstance(st, Exception):
            out.update(state=st.state, state_name=P.STATE_NAMES.get(st.state, f"Zustand {st.state}"),
                       warning_code=st.warnings, error_code=st.errors,
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
                    codes = self.kit.request(name).codes
                    if key == "warnings":
                        # Auf Wunsch ausgeblendete Warnungen (Standard: 81 Beschichter-Referenzfahrt)
                        out["hidden_warnings"] = [describe(c) for c in codes if c in IGNORED_WARNINGS]
                        codes = [c for c in codes if c not in IGNORED_WARNINGS]
                    out[key] = [describe(c) for c in codes]
                except P.ProtocolError as e:
                    snap[name] = e
        errs = [f"{k}: {v}" for k, v in snap.items() if isinstance(v, Exception)]
        out["message"] = "; ".join(errs)
        self._set(**out)
        try:
            PRINTLOG.update(self.snapshot())
        except Exception:
            pass

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
                if cmd.get("cmd") == "job_start":
                    self._start_job(str(cmd.get("id", "")), reply)
                    continue
                if cmd.get("cmd") == "lamps_full":
                    # Heizstrahler links/rechts/vorne auf volle Leistung (die Firmware speichert den Wert dauerhaft)
                    if self.snapshot().get("printing"):
                        raise ValueError("Während des Drucks gesperrt")
                    with self.usb:
                        for w in ("left", "right", "front"):
                            self.kit.command(P.cmd_lamp(w, 100), strict=True)
                            self._remember_lamp(w, 100.0)
                    reply.put({"ok": True})
                    continue
                payload = self._encode(cmd)
                strict = cmd.get("cmd") in ("scaling", "pattern", "targets", "laser_speed")
                motion = cmd.get("cmd") in ("move", "make_layer")
                if motion and self.snapshot().get("state") != P.STATE_POWDER_PREP:
                    # Wie Central: Fahren und Schicht auftragen nur in der Pulvervorbereitung
                    with self.usb:
                        self.kit.command(P.cmd_simple(P.COM_GO_POWDERPREPARATION))
                        st = self.kit.request("state")
                    self._set(state=st.state, state_name=P.STATE_NAMES.get(st.state, f"Zustand {st.state}"))
                try:
                    with self.usb:
                        # Central wertet auch bei Fahrbefehlen das Erfolgs-Byte aus („Printer reported unsuccessful …“)
                        self.kit.command(payload, strict=strict or motion)
                except P.ProtocolError as e:
                    if motion:
                        snap = self.snapshot()
                        why = [f"Zustand: {snap.get('state_name', '?')}"]
                        warn = [w.get("code") for w in snap.get("warnings", []) if isinstance(w, dict)]
                        if 80 in warn or 82 in warn:
                            why.append("Kit meldet Problem mit einer Plattform-Achse (80/82)")
                        raise P.ProtocolError(f"Kit führt die Bewegung nicht aus ({'; '.join(why)})") from e
                    raise
                if cmd.get("cmd") == "scaling":
                    self._read_scaling()
                if cmd.get("cmd") == "lamp":
                    self._remember_lamp(cmd["which"], float(cmd["percent"]))
                reply.put({"ok": True})
            except (P.ProtocolError, ValueError, KeyError) as e:
                reply.put({"ok": False, "error": str(e)})

    # -- Job-Bibliothek --------------------------------------------------------
    CURRENT_FILE = "aktueller-job.json"

    def set_current_job(self, meta: dict | None):
        """Job, den der Kit gerade druckt – für Schichtvorschau und Bauhöhe auf der Druckseite."""
        cur = None
        if meta:
            cur = {k: meta.get(k) for k in ("id", "name", "layers", "layer_mm", "height_mm", "bbox")}
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(os.path.join(STATE_DIR, self.CURRENT_FILE), "w") as f:
                json.dump(cur, f)
        except OSError:
            pass
        self._set(current_job=cur)

    def load_current_job(self):
        try:
            with open(os.path.join(STATE_DIR, self.CURRENT_FILE)) as f:
                self._set(current_job=json.load(f))
        except (OSError, ValueError):
            pass

    def _start_job(self, job_id: str, reply: queue.Queue):
        """Wie Central: Vorheizen an, Datei per FTPJ16 übertragen, Druck starten (bei Fehler Vorheizen aus)."""
        from kitctl import ftp
        from kitd import jobs
        snap = self.snapshot()
        try:
            if snap.get("printing"):
                raise ValueError("Der Kit druckt bereits")
            meta = jobs.get(job_id)
            if meta.get("source") == "demo" and not self.demo:
                raise ValueError("Der Beispieljob läuft nur im Demo-Modus")
            data = jobs.data(job_id)
        except ValueError as e:
            reply.put({"ok": False, "error": str(e)})
            return
        reply.put({"ok": True})
        tr = {"id": job_id, "name": meta["name"], "sent": 0, "total": len(data), "phase": "Vorheizen einschalten", "error": ""}
        self._set(transfer=dict(tr))
        last = [0.0]

        def progress(sent, total):
            if time.time() - last[0] > 0.25 or sent == total:
                last[0] = time.time()
                tr.update(sent=sent, phase="Übertrage Job zum Kit")
                self._set(transfer=dict(tr))

        warm = False
        try:
            with self.usb:
                tr["phase"] = "Kit bereit machen"
                self._set(transfer=dict(tr))
                ready = self._wait_idle()
                prof = meta.get("profile")
                warn = []
                if prof and not ready:
                    warn = ["Pulverprofil (Kit blieb im Vorheizen)"]
                elif prof:
                    # Central setzt beim Start gar kein Profil (nur Vorheizen, Job, Start). Lehnt die Firmware einen
                    # Profilwert ab, starten wir trotzdem mit den Werten, die am Kit eingestellt sind, und melden es.
                    tr["phase"] = "Pulverprofil einstellen"
                    self._set(transfer=dict(tr))
                    warn = self._apply_profile(prof)
                tr["phase"] = "Vorheizen einschalten"
                self._strict(P.cmd_warmup(True), "Vorheizen")
                warm = True
                ftp.send_file(self.kit.t, data, ftp.PRINT_FILE, progress=progress)
                tr["phase"] = "Druck starten"
                self._set(transfer=dict(tr))
                self.kit.command(P.cmd_simple(P.COM_STARTPRINT), strict=True)
            jobs.update(job_id, last_started=time.time(), starts=int(meta.get("starts") or 0) + 1)
            self.set_current_job(meta)
            res = {"ok": True, "name": meta["name"], "ts": time.time()}
            if warn:
                res["warn"] = "nicht übernommen: " + ", ".join(warn) + " – es gelten die Werte am Kit"
            self._set(transfer=None, job_result=res)
        except Exception as e:
            if warm:
                try:
                    with self.usb:
                        self.kit.command(P.cmd_warmup(False))
                except Exception:
                    pass
            msg = f"{tr['phase']}: {str(e) or e.__class__.__name__}"
            self._set(transfer=None, job_result={"ok": False, "name": meta["name"], "error": msg, "ts": time.time()})
            if isinstance(e, (OSError,)) and not isinstance(e, ftp.TransferError):
                raise   # USB weg -> Hauptschleife verbindet neu

    def _wait_idle(self, timeout: float = 20.0) -> bool:
        """Vor dem Start soll der Kit „Bereit“ sein, sonst lehnt die Firmware Sollwerte ab:
        Pulvervorbereitung beenden bzw. ein schon laufendes Vorheizen kurz ausschalten (es wird gleich wieder
        eingeschaltet) und warten. Liefert False, wenn der Kit im Vorheizen bleibt – dann wird ohne Profil
        gestartet, wie bei Central (Vorheizen, Job, Start). Andere Zustände (Tür offen, Fehler) brechen ab."""
        t_end = time.time() + timeout
        sent = set()
        st = None
        while time.time() < t_end:
            try:
                st = self.kit.request("state").state
            except P.ProtocolError:
                st = None
            if st == P.STATE_IDLE:
                self._set(state=st, state_name=P.STATE_NAMES.get(st, f"Zustand {st}"))
                return True
            if st == P.STATE_POWDER_PREP and "prep" not in sent:
                self.kit.command(P.cmd_simple(P.COM_EXIT_POWDERPREPARATION))
                sent.add("prep")
            elif st in (5, 6) and "warm" not in sent:
                self.kit.command(P.cmd_warmup(False))
                sent.add("warm")
            time.sleep(0.5)
        if st in (5, 6):
            return False
        name = P.STATE_NAMES.get(st, f"Zustand {st}") if st is not None else "unbekannt"
        raise ValueError(f"Kit ist nicht bereit ({name}) – Tür zu? Fehler am Kit quittiert?")

    def _strict(self, payload: bytes, what: str, tries: int = 3):
        """Befehl mit Erfolgs-Prüfung; die Firmware lehnt direkt nach einem Zustandswechsel gern kurz ab."""
        for n in range(tries):
            try:
                return self.kit.command(payload, strict=True)
            except P.ProtocolError as e:
                if n == tries - 1:
                    raise P.ProtocolError(f"{what}: {e}") from e
                time.sleep(1.0)

    def _apply_profile(self, prof: dict) -> list:
        """Sollwerte, Lasergeschwindigkeit und Heizstrahler aus dem Pulverprofil des Jobs (falls angegeben).
        Ungültige Werte im Profil brechen ab; lehnt die Firmware einen Wert ab, wird er übersprungen.
        Liefert die Namen der abgelehnten Werte."""
        failed = []

        def send(payload, what):
            try:
                self._strict(payload, what, tries=2)
                return True
            except P.ProtocolError as e:
                print(f"Profil: {e}", flush=True)
                failed.append(what)
                return False
        t = prof.get("temps")
        if t:
            vals = [float(t[k]) for k in ("surface_warmup", "chamber_warmup", "surface_print", "chamber_print")]
            for v, lim in zip(vals, (P.MAX_SURFACE, P.MAX_CHAMBER, P.MAX_SURFACE, P.MAX_CHAMBER)):
                if not 0 <= v <= lim:
                    raise ValueError(f"Profil: Temperatur außerhalb 0–{lim:g} °C")
            send(P.cmd_targets(*vals), "Solltemperaturen")
        for key, which in (("laser_speed_mm_s", "general"), ("contour_speed_mm_s", "contour")):
            if prof.get(key) is not None:
                v = float(prof[key])
                if not P.MIN_LASER <= v <= P.MAX_LASER:
                    raise ValueError("Profil: Lasergeschwindigkeit außerhalb des erlaubten Bereichs")
                send(P.cmd_laser_speed(which, v), "Lasergeschwindigkeit" + (" Kontur" if which == "contour" else ""))
        for w, pct in (prof.get("lamps") or {}).items():
            if w in ("left", "right", "front") and 0 <= float(pct) <= 100:
                if send(P.cmd_lamp(w, float(pct)), "Heizstrahler"):
                    self._remember_lamp(w, float(pct))
        return sorted(set(failed), key=failed.index)

    def ready_for_net_start(self) -> str:
        """Leer, wenn ein Job aus dem Netz gestartet werden darf, sonst der Grund."""
        s = self.snapshot()
        if not s.get("connected"):
            return "Kein Kit verbunden"
        if s.get("printing"):
            return "Der Kit druckt bereits"
        if s.get("transfer"):
            return "Es wird gerade ein Job übertragen"
        if s.get("errors"):
            return "Kit meldet Fehler: " + ", ".join(str(e.get("title", e)) if isinstance(e, dict) else str(e) for e in s["errors"])
        if s.get("waiting_for_sd"):
            return "Kit wartet auf SD-Karte"
        return ""

    def _encode(self, c: dict) -> bytes:
        name = c.get("cmd")
        printing = self.snapshot().get("printing", False)
        motion = {"move", "make_layer", "powder_prep_on", "pattern", "scaling", "exit_calibration", "targets", "laser_speed"}
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
            # Central stellt die Lampenleistung beim Kit nie ein; die Firmware speichert sie dauerhaft
            # und kann sie nicht zurückmelden. Nur bewusst aus dem Experten-Dialog (Werte merkt sich der Pi).
            if not c.get("expert"):
                raise ValueError("Lampenleistung nur im Experten-Dialog")
            pct = float(c["percent"])
            if not 10 <= pct <= 100:
                raise ValueError("Heizstrahler 10–100 %")
            return P.cmd_lamp(c["which"], pct)
        if name == "lamp_legacy":
            return P.cmd_lamp(c["which"], float(c["percent"]))
        if name == "target":
            t = float(c["celsius"])
            lim = P.MAX_CHAMBER if c["which"].startswith("chamber") else P.MAX_SURFACE
            if not 0 <= t <= lim:
                raise ValueError(f"Temperatur 0–{lim:g} °C")
            return P.cmd_target(c["which"], t)
        if name == "targets":   # alle vier Sollwerte wie Central „Send parameters to Sintratec Kit“
            sw, cw, sp, cp = (float(c[k]) for k in ("surface_warmup", "chamber_warmup", "surface_print", "chamber_print"))
            for v, lim in ((sw, P.MAX_SURFACE), (sp, P.MAX_SURFACE), (cw, P.MAX_CHAMBER), (cp, P.MAX_CHAMBER)):
                if not 0 <= v <= lim:
                    raise ValueError(f"Temperatur außerhalb 0–{lim:g} °C")
            return P.cmd_targets(sw, cw, sp, cp)
        if name == "laser_speed":
            v = float(c["mm_s"])
            if not P.MIN_LASER <= v <= P.MAX_LASER:
                raise ValueError(f"Lasergeschwindigkeit {P.MIN_LASER:g}–{P.MAX_LASER:g} mm/s")
            return P.cmd_laser_speed("general", v)
        if name == "pattern":
            if c.get("name") not in P.PATTERNS:
                raise ValueError("unbekanntes Muster")
            if c["name"] == "home" and c.get("confirmed") is not True:
                # Grundsatz: Der Pi stößt die Referenzfahrt nie selbst an – nur nach Bestätigung am Bildschirm
                raise ValueError("Referenzfahrt nur nach Bestätigung am Bildschirm")
            return P.cmd_test_pattern(c["name"])
        if name == "scaling":
            return P.cmd_scaling(*(P.scaling_factor(float(c[k])) for k in "xyz"))
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
        if self.path == "/api/update":
            from kitd import update
            return self._json(update.status())
        if self.path.startswith("/api/wifi"):
            from kitd import wifi
            return self._json(wifi.status(rescan="rescan=1" in self.path))
        if self.path == "/api/jobs":
            from kitd import jobs
            if WORKER.demo:
                jobs.ensure_demo()
            # Der Beispieljob erscheint nur im Demo-Modus – nie versehentlich auf dem echten Kit drucken
            lst = [j for j in jobs.listing() if WORKER.demo or j.get("source") != "demo"]
            return self._json({"jobs": lst, **jobs.settings()})
        if self.path.startswith("/api/jobs/"):
            from kitd import jobs
            parts = self.path.split("/")   # /api/jobs/<id>/layer/<n>
            try:
                if len(parts) == 6 and parts[4] == "layer":
                    return self._json(jobs.layer(parts[3], int(parts[5])))
            except (ValueError, KeyError) as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if self.path == "/api/printlog":
            return self._json({"prints": PRINTLOG.all()})
        if self.path == "/api/state":
            st = WORKER.snapshot()
            try:
                from kitd.bridge import STATE as BR
                st["central"] = BR["central"]; st["central_peer"] = BR["peer"]
                from kitd.bridge import pc_link
                st["pc_link"] = pc_link()
            except Exception:
                pass
            return self._json(st)
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
        path = self.path.split("?")[0]
        # Handy-Oberfläche: http://<pi>:8080/app
        path = "index.html" if path in ("/", "/index.html") else "phone.html" if path in ("/app", "/app/") else path.lstrip("/")
        f = (UI_DIR / path).resolve()
        if not f.is_relative_to(UI_DIR.resolve()) or not f.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css",
                 "png": "image/png", "svg": "image/svg+xml",
                 "webmanifest": "application/manifest+json"}.get(f.suffix.lstrip("."), "application/octet-stream")
        data = f.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _upload_job(self):
        """Druckdatei von der PC-App annehmen; mit X-Job-Start: 1 gleich starten, wenn der Kit bereit ist."""
        import base64
        import urllib.parse
        from kitd import jobs
        if not NET_JOBS:
            return self._json({"ok": False, "error": "Jobs aus dem Netz sind am Pi abgeschaltet"}, HTTPStatus.FORBIDDEN)
        try:
            from kitd.bridge import _allowed
            if not _allowed(self.client_address[0]):
                return self._json({"ok": False, "error": "Gerät nicht erlaubt"}, HTTPStatus.FORBIDDEN)
        except ImportError:
            pass
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_UPLOAD:
            return self._json({"ok": False, "error": "Datei fehlt oder ist zu groß"}, HTTPStatus.BAD_REQUEST)
        buf = bytearray()
        while len(buf) < n:
            chunk = self.rfile.read(min(1 << 20, n - len(buf)))
            if not chunk:
                return self._json({"ok": False, "error": "Übertragung abgebrochen"}, HTTPStatus.BAD_REQUEST)
            buf += chunk
        name = urllib.parse.unquote(self.headers.get("X-Job-Name", ""))[:80]
        profile = None
        if self.headers.get("X-Job-Profile"):
            try:
                profile = json.loads(base64.b64decode(self.headers["X-Job-Profile"]))
                if not isinstance(profile, dict):
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                return self._json({"ok": False, "error": "Profil unlesbar"}, HTTPStatus.BAD_REQUEST)
        meta = jobs.save(bytes(buf), "pc", name)
        if profile:
            keep = {k: profile.get(k) for k in ("name", "temps", "laser_speed_mm_s", "contour_speed_mm_s", "lamps")}
            jobs.update(meta["id"], profile=keep)
            meta["profile"] = keep
        if meta.get("error"):
            return self._json({"ok": False, "job": meta, "started": False, "error": "Datei ungültig: " + meta["error"]})
        res = {"ok": True, "job": meta, "started": False}
        if self.headers.get("X-Job-Start") == "1":
            why = "Starten aus dem Netz ist am Pi abgeschaltet" if not NET_START else WORKER.ready_for_net_start()
            if why:
                res["start_error"] = why + " – Job liegt in der Bibliothek"
            else:
                r = WORKER.submit({"cmd": "job_start", "id": meta["id"]})
                res["started"] = bool(r.get("ok"))
                if not r.get("ok"):
                    res["start_error"] = r.get("error", "Start fehlgeschlagen")
        return self._json(res)

    def do_DELETE(self):
        """Job aus der Bibliothek löschen – von der PC-App, gleiche Freigabe wie beim Senden."""
        import urllib.parse
        from kitd import jobs
        parts = self.path.split("/")      # /api/jobs/<id>
        if len(parts) != 4 or parts[1:3] != ["api", "jobs"]:
            return self._json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
        if not NET_JOBS:
            return self._json({"ok": False, "error": "Jobs aus dem Netz sind am Pi abgeschaltet"}, HTTPStatus.FORBIDDEN)
        try:
            from kitd.bridge import _allowed
            if not _allowed(self.client_address[0]):
                return self._json({"ok": False, "error": "Gerät nicht erlaubt"}, HTTPStatus.FORBIDDEN)
        except ImportError:
            pass
        job_id = urllib.parse.unquote(parts[3])
        try:
            if (WORKER.snapshot().get("transfer") or {}).get("id") == job_id:
                raise ValueError("Job wird gerade übertragen")
            jobs.get(job_id)
            jobs.delete(job_id)
            return self._json({"ok": True})
        except (ValueError, OSError) as e:
            return self._json({"ok": False, "error": str(e)})

    def _remote_denied(self, cmd: dict) -> str:
        """Leer, wenn der PC diesen Befehl schicken darf, sonst der Grund."""
        name = cmd.get("cmd")
        try:
            from kitd.bridge import _allowed
            if not _allowed(self.client_address[0]):
                return "Gerät nicht erlaubt"
        except ImportError:
            pass
        if name in LOCAL_ONLY:
            return "Nur am Kit Control bedienbar"
        if not remote_enabled():
            return "Bedienung vom PC ist am Kit ausgeschaltet – am Display unter System → „Bedienung vom PC“ einschalten"
        st = WORKER.snapshot()
        stop = name in STOP_CMDS or (name == "warmup" and cmd.get("on") is False)
        if (st.get("printing") or st.get("transfer")) and not stop:
            return "Während eines Drucks ist die Bedienung vom PC gesperrt – nur Abbrechen und Abkühlen"
        if name == "job_start" and not NET_START:
            return "Starten aus dem Netz ist am Pi abgeschaltet"
        if name == "pattern" and cmd.get("name") == "home":
            return "Referenzfahrt nur am Kit Control"
        return ""

    def do_POST(self):
        if self.path == "/api/jobs":
            return self._upload_job()
        if self.path != "/api/cmd":
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        local = self.client_address[0] in ("127.0.0.1", "::1")
        try:
            n = int(self.headers.get("Content-Length", "0"))
            cmd = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            if not isinstance(cmd, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self._json({"ok": False, "error": "ungültige Anfrage"}, HTTPStatus.BAD_REQUEST)
        if not local:
            why = self._remote_denied(cmd)
            if why:
                return self._json({"ok": False, "error": why}, HTTPStatus.FORBIDDEN)
        if cmd.get("cmd") == "remote_control":
            try:
                set_remote(bool(cmd.get("on")))
                return self._json({"ok": True})
            except OSError as e:
                return self._json({"ok": False, "error": str(e)})
        if cmd.get("cmd") == "pc_link":
            mode = cmd.get("mode")
            if mode not in ("wlan", "usb"):
                return self._json({"ok": False, "error": "wlan oder usb"})
            if DEMO:
                open("/tmp/kit-pc-link", "w").write(mode)
                return self._json({"ok": True})
            import subprocess
            r = subprocess.run(["sudo", "-n", "/opt/kit-controller/system/kit-pclink.sh", mode], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                return self._json({"ok": False, "error": (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "Umschalten fehlgeschlagen"})
            return self._json({"ok": True})
        if cmd.get("cmd") in ("update_check", "update_start"):
            from kitd import update
            if cmd["cmd"] == "update_check":
                return self._json({"ok": True, "update": update.check()})
            if WORKER.snapshot().get("printing"):
                return self._json({"ok": False, "error": "Während des Drucks kein Update"})
            try:
                update.start()
                return self._json({"ok": True})
            except ValueError as e:
                return self._json({"ok": False, "error": str(e)})
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
        if cmd.get("cmd") in ("job_delete", "job_autostart"):
            from kitd import jobs
            try:
                if cmd["cmd"] == "job_delete":
                    if (WORKER.snapshot().get("transfer") or {}).get("id") == cmd.get("id"):
                        raise ValueError("Job wird gerade übertragen")
                    jobs.delete(str(cmd.get("id", "")))
                else:
                    jobs.set_autostart(bool(cmd.get("on")))
                return self._json({"ok": True})
            except (ValueError, OSError) as e:
                return self._json({"ok": False, "error": str(e)})
        if cmd.get("cmd") == "demo":
            WORKER.want_demo = bool(cmd.get("on"))
            return self._json({"ok": True})
        if cmd.get("cmd") in ("reboot", "poweroff"):
            st = WORKER.snapshot()
            if st.get("transfer"):
                return self._json({"ok": False, "error": "Es wird gerade ein Job zum Kit übertragen"})
            if cmd["cmd"] == "poweroff" and st.get("printing"):
                return self._json({"ok": False, "error": "Während des Drucks nicht ausschalten – erst nach dem Druck"})
            if DEMO:
                return self._json({"ok": True})
            import subprocess
            subprocess.Popen(["sudo", "-n", "/usr/bin/systemctl", cmd["cmd"]])
            return self._json({"ok": True})
        self._json(WORKER.submit(cmd))


def main():
    WORKER.load_current_job()
    WORKER.start()
    if os.environ.get("KIT_BRIDGE", "1") == "1":
        from kitd.bridge import start_bridge
        start_bridge(WORKER)
    host = os.environ.get("KIT_HOST", "0.0.0.0")   # Lesen aus dem Netz für die PC-App; Bedienung bleibt lokal
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
