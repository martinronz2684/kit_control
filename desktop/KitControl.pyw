"""Startdatei der Desktop-App (ohne Konsolenfenster unter Windows)."""
import multiprocessing
import sys

if __name__ == "__main__":
    # Pflicht für das Slicen auf mehreren Kernen in der gebauten App: Hilfsprozesse starten hier
    # nicht noch einmal die Oberfläche, sondern nur ihre Rechenarbeit.
    multiprocessing.freeze_support()
    from kitcontrol.main import main
    sys.exit(main())
