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
    mouse = None
    if "--selftest-mouse" in sys.argv:
        mouse = shots = sys.argv[sys.argv.index("--selftest-mouse") + 1]
        os.environ["KIT_PROFILE_DIR"] = os.path.join(shots, "_profile")
    elif "--screenshots" in sys.argv:
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
    if mouse:
        _selftest_mouse(app, engine, backend, mouse)
        return app.exec()
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
                r"Non-existent|is not installed|ReferenceError|TypeError|is not defined|Unable to assign|without a camera", p)]
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


def _selftest_mouse(app, engine, backend, out):
    """Prüfung mit echter 3D-Darstellung: Auto-Anordnen ansehen, ein Teil anklicken und mit der linken
    Maustaste ziehen (von oben und von vorne). Ergebnis als Zeilen „MAUS …“ und Bilder."""
    import numpy as np
    from PySide6.QtCore import QEvent, QMetaObject, QPointF, Qt, QTimer, Q_ARG, Q_RETURN_ARG
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtQuick import QQuickItem
    from kitslice import stl
    os.makedirs(out, exist_ok=True)

    def box(w, d, h, o=(0, 0, 0)):
        v = np.array([[x, y, z] for x in (0, w) for y in (0, d) for z in (0, h)], float) + o
        f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
             (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
        return v[np.array(f)]
    big = np.concatenate([box(56, 39, 6), box(14, 39, 20.7, (0, 0, 0)), box(56, 8, 14, (0, 31, 0)),
                          box(10, 10, 20.7, (40, 5, 0))])
    small = np.concatenate([box(10, 14.6, 4), box(10, 4, 19), box(10, 4, 19, (0, 10.6, 0))])
    paths = []
    for name, t in (("gross", big), ("klein", small)):
        pth = os.path.join(out, name + ".stl")
        stl.save_binary(t, pth)
        paths.append(pth)
    backend.addUrls([paths[0]] * 6 + [paths[1]] * 8)
    root = engine.rootObjects()[0]
    root.setProperty("width", 1360)
    root.setProperty("height", 860)
    log = []

    def say(t):
        print("MAUS " + t, flush=True)
        log.append(t)

    def vp():
        return root.findChild(QQuickItem, "viewport")

    def shot(name):
        root.grabWindow().save(os.path.join(out, name + ".png"))

    def screen_of(i):
        lo, hi = backend.core.scene.parts[i].bbox()
        c = (np.asarray(lo) + np.asarray(hi)) / 2
        v = vp()
        r = QMetaObject.invokeMethod(v, "screenPoint", Qt.DirectConnection, Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", float(c[0])), Q_ARG("QVariant", float(c[1])),
                                     Q_ARG("QVariant", float(hi[2])))
        pt = v.mapToScene(QPointF(r.x(), r.y()))
        return pt

    def send(kind, pt, buttons):
        btn = Qt.LeftButton if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) else Qt.NoButton
        ev = QMouseEvent(kind, pt, root.mapToGlobal(pt), btn, buttons, Qt.NoModifier)
        app.sendEvent(root, ev)

    steps = []

    def drag(view):
        def run():
            v = vp()
            if v is None:
                say("FEHLER: 3D-Ansicht nicht gefunden"); return
            v.setProperty("elev", 90 if view == "top" else 4)
            v.setProperty("yaw", 0)
            QTimer.singleShot(700, lambda: do(view))
        return run

    def do(view):
        i = 0
        p = backend.core.scene.parts[i]
        x0, y0, z0 = p.x, p.y, p.z_lift
        pt = screen_of(i)
        say(f"{view}: Teil 0 bei Bildpunkt {pt.x():.0f},{pt.y():.0f}; Position {x0:.1f},{y0:.1f},{z0:.1f}")
        backend.selected = -1
        before = [(q.x, q.y, q.z_lift) for q in backend.core.scene.parts]
        send(QEvent.MouseButtonPress, pt, Qt.LeftButton)
        say(f"{view}: nach Klick ausgewählt = {backend.selected}")
        for k in range(1, 11):
            send(QEvent.MouseMove, QPointF(pt.x() + 6 * k, pt.y() - 3 * k), Qt.LeftButton)
            app.processEvents()
        send(QEvent.MouseButtonRelease, QPointF(pt.x() + 60, pt.y() - 30), Qt.NoButton)
        app.processEvents()
        after = [(q.x, q.y, q.z_lift) for q in backend.core.scene.parts]
        ch = [(n, b, a) for n, (b, a) in enumerate(zip(before, after)) if sum(abs(u - v) for u, v in zip(b, a)) > 1]
        say(f"{view}: verschoben: " + ("; ".join(f"Teil {n} {tuple(round(v, 1) for v in b)} -> {tuple(round(v, 1) for v in a)}" for n, b, a in ch) or "FEHLER nichts"))
        shot("maus-" + view)
        QTimer.singleShot(300, nxt)

    def pack():
        r = backend.core.auto_pack(3.0, 2.0, True, False, 6.0)
        backend._parts_changed()
        say(f"Anordnen: {r}")
        v = vp()
        if v:
            v.setProperty("elev", 4); v.setProperty("yaw", 0)
        QTimer.singleShot(1500, lambda: (shot("anordnen-vorne"), QTimer.singleShot(200, nxt)))

    def iso():
        v = vp()
        if v:
            v.setProperty("elev", 26); v.setProperty("yaw", -32)
        QTimer.singleShot(1200, lambda: (shot("anordnen-3d"), QTimer.singleShot(200, nxt)))

    steps += [pack, iso, drag("top"), drag("front")]

    def nxt():
        if not steps:
            with open(os.path.join(out, "maus.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(log))
            app.exit(0)
            return
        steps.pop(0)()
    QTimer.singleShot(2500, nxt)


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
