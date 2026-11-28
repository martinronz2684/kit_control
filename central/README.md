# Central über WLAN

`usb4java-1.2.0.jar` ersetzt in Sintratec Central 1.2 die USB-Bibliothek. Central bleibt unverändert,
spricht aber übers Netz mit dem Kit Control am Pi statt direkt per USB mit dem Kit.
Display und Central können gleichzeitig arbeiten.

**Installieren (Windows):** [KitControl-Central-Setup.exe](https://github.com/martinronz2684/kit_control/releases/download/central-setup/KitControl-Central-Setup.exe)
herunterladen, Central schließen, ausführen. Das Setup findet Central, sichert die Original-Bibliothek
(`usb4java-1.2.0.jar.original`, zusätzlich im Setup-Ordner) und setzt die neue ein.
**Deinstallieren** über *Windows-Einstellungen → Apps → Kit Control für Sintratec Central* stellt das Original wieder her.
Nach einem Update von Central das Setup einfach erneut ausführen.

Ohne Setup geht es weiterhin per Skript: beide Dateien aus diesem Ordner in einen Ordner legen,
Central schließen, `Install-CentralWLAN.ps1` mit Rechtsklick → *Mit PowerShell ausführen*.

- **WLAN** (Standard am Pi): Der Pi wird im WLAN automatisch gefunden (UDP 8767). Klappt das nicht: `-IP <IP des Pi>`.
- **USB**: Am Display *System → PC-Verbindung → USB* wählen und den PC per USB-C-Kabel an den Pi anschließen.
  Der Pi erscheint am PC als Netzwerkadapter und hat dort immer `10.55.0.1` – die Bibliothek findet ihn von selbst.
  Den Pi dann über die GPIO-Pins oder ein Netzteil mit Datendurchleitung versorgen; ein PC-Anschluss liefert zu wenig Strom.
- Rückgängig: `-Uninstall` stellt die Original-Bibliothek wieder her.
- **Kopplung:** Beim ersten Verbinden zeigt das Kit-Display einen 6-stelligen Code, Central fragt ihn in einem
  Fenster ab. Danach meldet sich jede Verbindung mit dem dabei ausgehandelten Schlüssel an (liegt in
  `%APPDATA%\KitControl\central-pairing.properties`, geht nie übers Netz). Ohne Kopplung findet Central keinen Kit.
  Koppeln geht nicht, solange der Kit druckt, vorheizt oder Pulver vorbereitet. Entfernen: am Display unter
  *System → Gekoppelte Geräte*.
- Firmware- und Bootloader-Befehle werden vom Pi immer abgelehnt.
- Es kann immer nur ein Central gleichzeitig verbunden sein.

Quellcode: `src/org/usb4java/` (Java 8). Bauen: `javac --release 8 -d build src/org/usb4java/*.java && jar cf usb4java-1.2.0.jar -C build .`
