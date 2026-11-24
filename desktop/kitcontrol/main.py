"""Start der Desktop-App.  python -m kitcontrol.main  [datei.stl …] [--selftest]"""
from __future__ import annotations

import os
import sys


def _base() -> str:
    # PyInstaller entpackt nach sys._MEIPASS, sonst liegt alles neben dieser Datei
    return getattr(sys, "_MEIPASS", None) and os.path.join(sys._MEIPASS, "kitcontrol") or os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # desktop/
    if here not in sys.path:
        sys.path.insert(0, here)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    if "--selftest-slice" in sys.argv:
        return _selftest_slice()

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QFont, QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    from kitcontrol.backend import Backend
    try:
        from kitcontrol import geometry  # noqa: F401  (registriert MeshGeometry/LineGeometry für QML)
    except Exception as e:               # ohne Qt Quick 3D bleibt die einfache Ansicht
        print("3D-Ansicht ohne Grafikkarte:", e, file=sys.stderr)

    selftest = "--selftest" in sys.argv
    shots = None
    if "--screenshots" in sys.argv:
        shots = sys.argv[sys.argv.index("--screenshots") + 1]
        os.environ["KIT_PROFILE_DIR"] = os.path.join(shots, "_profile")
    files = [a for a in sys.argv[1:] if not a.startswith("--") and a != shots]

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Kit Control")
    app.setOrganizationName("Kit Control")
    app.setWindowIcon(QIcon(os.path.join(_base(), "assets", "mark.png")))
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))

    backend = Backend()
    engine = QQmlApplicationEngine()
    problems = []
    engine.warnings.connect(lambda ws: problems.extend(w.toString() for w in ws))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("assetDir", QUrl.fromLocalFile(os.path.join(_base(), "assets")).toString())
    engine.load(QUrl.fromLocalFile(os.path.join(_base(), "qml", "Main.qml")))
    if not engine.rootObjects():
        print("\n".join(problems) or "Oberfläche lädt nicht", file=sys.stderr)
        return 1

    projects = [f for f in files if f.lower().endswith(".kcp")]
    if projects:
        backend.loadProject(projects[0])
    stls = [f for f in files if f.lower().endswith(".stl")]
    if stls:
        backend.addUrls(stls)
    if shots:
        _screenshots(app, engine, backend, shots)
        return app.exec()
    if selftest:
        # Für die automatische Prüfung beim Bauen: Oberfläche laden, alle Seiten einmal zeigen, Fehler melden
        root = engine.rootObjects()[0]
        pages = [0]

        def step():
            if pages[0] < 5:
                root.setProperty("page", pages[0])
                pages[0] += 1
                return
            timer.stop()
            import re
            bad = [p for p in problems if re.search(
                r"is not a type|Cannot assign|Invalid property|Expected token|Syntax error|failed to load|"
                r"Non-existent|is not installed|ReferenceError|TypeError|is not defined|Unable to assign", p)]
            for p in problems:
                print(("FEHLER " if p in bad else "Hinweis ") + p, file=sys.stderr)
            app.exit(1 if bad else 0)
        timer = QTimer()
        timer.timeout.connect(step)
        timer.start(400)
    else:
        backend.check_update()
        backend.discover()
    return app.exec()


def _screenshots(app, engine, backend, out):
    """Für die Prüfung beim Bauen: Beispielteile laden, slicen und von jeder Seite ein Bild speichern."""
    import numpy as np
    from PySide6.QtCore import QTimer
    from kitslice import stl
    os.makedirs(out, exist_ok=True)

    def box(w, d, h):
        v = np.array([[x, y, z] for x in (0, w) for y in (0, d) for z in (0, h)], float)
        f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
             (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
        return v[np.array(f)]
    u, v = np.meshgrid(np.linspace(0, np.pi, 40), np.linspace(0, 2 * np.pi, 80))
    P = np.stack([np.sin(u) * np.cos(v) * 12, np.sin(u) * np.sin(v) * 7, np.cos(u) * 5 + 5], -1)
    a, b, c, d = P[:-1, :-1], P[1:, :-1], P[1:, 1:], P[:-1, 1:]
    ell = np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)])
    paths = []
    for name, t in (("Halter", box(30, 20, 12)), ("Linse", ell)):
        pth = os.path.join(out, name + ".stl")
        stl.save_binary(t, pth)
        paths.append(pth)
    backend.addUrls(paths + paths)
    backend.core.slice()
    backend._slice_state = "done"
    backend.sliceChanged.emit()
    root = engine.rootObjects()[0]
    root.setProperty("width", 1360)
    root.setProperty("height", 860)
    steps = list(range(5))
    names = ["1-platzieren", "2-parameter", "3-vorschau", "4-pulver", "5-drucken"]

    def shoot():
        if not steps:
            app.exit(0)
            return
        i = steps[0]
        if root.property("page") != i:
            root.setProperty("page", i)
            QTimer.singleShot(900, shoot)
            return
        steps.pop(0)
        img = root.grabWindow()
        img.save(os.path.join(out, names[i] + ".png"))
        QTimer.singleShot(100, shoot)
    QTimer.singleShot(1500, shoot)


def _selftest_slice() -> int:
    """Für die Prüfung beim Bauen: Slicen auf mehreren Kernen in der gebauten App."""
    import numpy as np
    from kitslice import profiles as PR
    from kitslice.slicer import SliceSettings, slice_mesh
    v = np.array([[x, y, z] for x in (-20, 20) for y in (-20, 20) for z in (0, 30)], float)
    f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
         (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    tris = v[np.array(f)]
    s = SliceSettings.from_profile(PR.validate(PR.get("pa12")))
    from kitslice import slicer
    layers = slicer._slice_parallel(*slicer.index_mesh(tris), s, 300, 2, None, None)
    ok = len(layers) == 300 and all(L is not None and len(L.hatches) for L in layers)
    print("Selbsttest Slicen auf mehreren Kernen:", "ok" if ok else "FEHLER")
    return 0 if ok else 1


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
