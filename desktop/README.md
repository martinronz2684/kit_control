# Kit Control Desktop (PC)

Gegenstück zu Sintratec Central am PC – mit eigenem Slicer, speicherbaren Pulverprofilen und direkter
Verbindung zum Kit Control am Pi (WLAN/LAN oder USB-Netz).

| Ordner | Inhalt |
|---|---|
| `kitcontrol/` | Die App: Oberfläche (Qt/QML, `qml/`), Logik (`core.py`), Update-Abfrage (`updater.py`) |
| `kitslice/` | Slicer (STL → Druckdatei wie Central), Bauraum/Anordnen, Pulverprofile, Verbindung zum Pi |
| `setup/` | Windows-Setup (Inno Setup), Logo und Bilder für den Installer |

## Installieren (Windows)
**KitControl-Setup.exe** vom Release „desktop-setup“ herunterladen und ausführen – fertig, keine Konsole,
kein Python nötig. Startmenü, optional Desktop-Verknüpfung und „Öffnen mit“ für STL-Dateien.
Die App fragt bei jedem Start auf GitHub nach einer neuen Version und bietet sie oben im Fenster an
(klappt ohne Anmeldung nur, wenn das Repository öffentlich ist).

Das Setup baut GitHub Actions bei jeder Änderung in `desktop/` automatisch (`.github/workflows/desktop-setup.yml`).

## Bedienung vom PC
Live-Verfolgung und Job senden gehen sofort. Heizen, Abbrechen und Pulver fahren vom PC aus erlaubt der Pi
erst nach Freigabe: in `/etc/kit/kitd.env` `KIT_REMOTE=1` setzen und `sudo systemctl restart kitd`.

## Entwickeln
```bash
cd desktop
pip install -r requirements.txt
python KitControl.pyw
```

```bash
cd desktop
python3 -m kitslice.cli slice teil.stl --profile pa12 -o job.bin
python3 -m kitslice.cli slice teil.stl --send <IP des Pi> --start
```
Braucht Python 3.9+ und numpy.
