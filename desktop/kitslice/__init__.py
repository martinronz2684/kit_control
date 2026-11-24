"""kitslice – eigener Slicer für den Sintratec Kit (Ersatz für den Build-Processor aus Central 1.2.0).

Nachgebaut nach dem Bytecode von sintratec-build-processor-1.2.0 und sintratec-central-kit-1.2.0:
  - Koordinaten in mm, Bauraum um den Ursprung zentriert (Central clippt auf ±X/2, ±Y/2; bevorzugt 110 mm)
  - Konturen: Querschnitt um die Konturversätze nach innen versetzt (Perimeter, kumulativ), äußerste zuerst
  - Füllung: Querschnitt um den Füllversatz nach innen versetzt (gemessen vom Originalrand),
    Schraffur auf einem festen Raster y = k * Abstand im um den Schichtwinkel gedrehten System,
    Winkel pro Schicht reihum (Hatch4x90: 45°, -45°, -135°, 135°), Linien von oben nach unten, im Zickzack
  - Kontur vor Füllung, Mindestvektorlänge 25 µm, höchstens 20 leere Schichten am Stück
"""

__version__ = "0.1.0"

# kitctl (Druckdatei-Format, Protokoll) liegt eine Ebene höher im Repo und wird mit dem Pi geteilt
import os as _os
import sys as _sys

_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
try:
    import kitctl as _k  # noqa: F401
except ImportError:
    _sys.path.insert(0, _root)
