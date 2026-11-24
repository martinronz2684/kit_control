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

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QFont, QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    from kitcontrol.backend import Backend

    selftest = "--selftest" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]

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


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
