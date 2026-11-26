#!/usr/bin/env python3
"""Bildschirmfotos der Kit-Oberfläche (app/Main.qml) – für die Kontrolle in der CI.

Startet kitd im Demo-Modus, lädt die Oberfläche ohne Bildschirm in 800×450 (ungedreht) und
fotografiert jede Seite: einmal im Leerlauf, einmal während eines (simulierten) Drucks.
Aufruf: python tools/kit-shots.py <Zielordner>
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "kitshots")
PAGES = ["print", "move", "heat", "jobs", "cal", "params", "sys"]


def api(path, body=None):
    req = urllib.request.Request("http://127.0.0.1:8080" + path, method="POST" if body else "GET",
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    env = dict(os.environ, KIT_DEMO="1", KIT_PORT="8080", KIT_BRIDGE="0", KIT_STATE_DIR=tempfile.mkdtemp(),
               PYTHONPATH=ROOT)
    kitd = subprocess.Popen([sys.executable, "-m", "kitd.server"], cwd=ROOT, env=env,
                            stdout=open(os.path.join(OUT, "kitd.log"), "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                api("/api/state")
                break
            except Exception:
                time.sleep(0.2)
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")   # Software-Zeichnen: Fenster lässt sich abfotografieren
        from PySide6.QtCore import QObject, QTimer, QUrl
        from PySide6.QtGui import QGuiApplication, QWindow
        from PySide6.QtQml import QQmlApplicationEngine
        app = QGuiApplication(sys.argv[:1])
        eng = QQmlApplicationEngine()
        log = []
        eng.warnings.connect(lambda ws: log.extend(w.toString() for w in ws))
        eng.load(QUrl.fromLocalFile(os.path.join(ROOT, "app", "Main.qml")))
        if not eng.rootObjects():
            print("Oberfläche lädt nicht:\n" + "\n".join(log))
            return 1
        win = eng.rootObjects()[0]
        win.setProperty("updOffered", True)          # Demo meldet immer ein Update – Angebot beim Start unterdrücken
        win.setProperty("visibility", QWindow.Windowed)
        win.resize(800, 450)

        def wait(ms):
            end = time.time() + ms / 1000
            while time.time() < end:
                app.processEvents()
                time.sleep(0.02)

        def shoot(name):
            wait(900)
            img = app.primaryScreen().grabWindow(win.winId(), 0, 0, 800, 450)
            img.save(os.path.join(OUT, name + ".png"))

        wait(3000)                                   # Startbild ausblenden, ersten Zustand holen
        for p in PAGES:
            win.setProperty("page", p)
            shoot(f"idle-{p}")
        # Druck simulieren: ersten Demo-Job starten
        try:
            jid = api("/api/jobs")["jobs"][0]["id"]
            api("/api/cmd", {"cmd": "job_start", "id": jid})
            for _ in range(60):
                if api("/api/state").get("printing"):
                    break
                wait(500)
            wait(4000)
        except Exception as e:
            log.append(f"Druck nicht gestartet: {e}")
        for p in PAGES:
            win.setProperty("page", p)
            shoot(f"print-{p}")
        # Software-Fenster einmal zeigen
        win.setProperty("page", "sys")
        upd = win.findChild(QObject, "updOvl")
        if upd is not None:
            upd.setProperty("visible", True)
            shoot("overlay-update")
        with open(os.path.join(OUT, "qml.log"), "w") as f:
            f.write("\n".join(log))
        print("\n".join(log[-30:]))
        print("Fotos:", sorted(os.listdir(OUT)))
        return 0
    finally:
        kitd.terminate()


if __name__ == "__main__":
    sys.exit(main())
