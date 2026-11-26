"""Schichtzeiten echter Drucke mitschreiben – damit Kit Control die Druckzeit realistisch schätzen kann.

Je Schicht: Dauer vom Beginn dieser Schicht bis zum Beginn der nächsten (Laser + Beschichten +
Aufwärmen der frischen Pulverschicht), dazu Laserweg und Leerweg der Schicht aus der Druckdatei und
die Lasergeschwindigkeit, die der Kit dabei gemeldet hat. Gespeichert werden die letzten Drucke.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time

KEEP_PRINTS = 8
MAX_ROWS = 1500


class PrintLog:
    def __init__(self, state_dir: str):
        self.file = os.path.join(state_dir, "printlog.json")
        self.lock = threading.Lock()
        self.cur: dict | None = None          # laufender Druck
        self.last_layer = None
        self.last_t = 0.0

    # -- Mitschreiben (aus der Abfrageschleife, etwa jede Sekunde) -------------------------------
    def update(self, st: dict) -> None:
        now = time.time()
        printing = bool(st.get("printing"))
        job = st.get("current_job") or {}
        layer = st.get("layer")
        with self.lock:
            if printing and self.cur is None:
                self.cur = {"job_id": job.get("id", ""), "name": job.get("name", ""), "start": int(now),
                            "layer_mm": job.get("layer_mm"), "rows": []}
                self.last_layer, self.last_t = layer, now
                return
            if self.cur is None:
                return
            if printing and isinstance(layer, int) and layer != self.last_layer:
                # nur lückenlos beobachtete Schichten zählen (kein Neustart der Abfrage dazwischen)
                if isinstance(self.last_layer, int) and layer == self.last_layer + 1 and self.last_t:
                    if len(self.cur["rows"]) < MAX_ROWS:
                        self.cur["rows"].append([self.last_layer, round(now - self.last_t, 1), None, None,
                                                 st.get("laser_speed")])
                self.last_layer, self.last_t = layer, now
            if not printing:
                done, self.cur = self.cur, None
                self.last_layer, self.last_t = None, 0.0
                threading.Thread(target=self._finish, args=(done,), daemon=True).start()

    # -- Abschluss: Laser- und Leerweg je Schicht aus der Druckdatei ------------------------------
    @staticmethod
    def _lengths(job_id: str, n: int):
        from kitd import jobs
        L = jobs.layer(job_id, n)
        scan = jump = 0.0
        last = None
        for key in ("contour", "infill"):
            a = L.get(key) or []
            for i in range(0, len(a) - 3, 4):
                x1, y1, x2, y2 = a[i:i + 4]
                scan += math.hypot(x2 - x1, y2 - y1)
                if last is not None:
                    jump += math.hypot(x1 - last[0], y1 - last[1])
                last = (x2, y2)
        return round(scan, 1), round(jump, 1)

    def _fill(self, rec: dict) -> dict:
        for r in rec["rows"]:
            if r[2] is None and rec.get("job_id"):
                try:
                    r[2], r[3] = self._lengths(rec["job_id"], int(r[0]))
                except Exception:
                    r[2], r[3] = None, None
        return rec

    def _finish(self, rec: dict) -> None:
        if len(rec.get("rows", [])) < 5:
            return
        self._fill(rec)
        rec["end"] = int(time.time())
        with self.lock:
            data = self._load()
            data.append(rec)
            data = data[-KEEP_PRINTS:]
            tmp = self.file + ".tmp"
            try:
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self.file)
            except OSError:
                pass

    def _load(self) -> list:
        try:
            with open(self.file) as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def all(self) -> list:
        """Gespeicherte Drucke plus der laufende (Längen werden dafür nachgerechnet)."""
        with self.lock:
            data = self._load()
            cur = json.loads(json.dumps(self.cur)) if self.cur else None
        if cur and cur["rows"]:
            cur["running"] = True
            data.append(self._fill(cur))
        return data
