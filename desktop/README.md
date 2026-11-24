# Kit Control Desktop (PC)

Gegenstück zu Sintratec Central am PC – mit eigenem Slicer, speicherbaren Pulverprofilen und direkter
Verbindung zum Kit Control am Pi (WLAN/LAN oder USB-Netz).

| Ordner | Inhalt |
|---|---|
| `kitslice/` | Slicer (STL → Druckdatei wie Central), Bauraum/Anordnen, Pulverprofile, Verbindung zum Pi |

Die Oberfläche, das Windows-Setup und die Update-Abfrage folgen hier.

```bash
cd desktop
python3 -m kitslice.cli slice teil.stl --profile pa12 -o job.bin
python3 -m kitslice.cli slice teil.stl --send <IP des Pi> --start
```
Braucht Python 3.9+ und numpy.
