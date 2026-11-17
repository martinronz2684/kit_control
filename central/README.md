# Central über WLAN

`usb4java-1.2.0.jar` ersetzt in Sintratec Central 1.2 die USB-Bibliothek. Central bleibt unverändert,
spricht aber übers Netz mit dem Kit Control am Pi statt direkt per USB mit dem Kit.
Display und Central können gleichzeitig arbeiten.

**Installieren (Windows):** beide Dateien aus diesem Ordner in einen Ordner legen,
Central schließen, `Install-CentralWLAN.ps1` mit Rechtsklick → *Mit PowerShell ausführen*.

- Der Pi wird im WLAN automatisch gefunden (UDP 8767). Klappt das nicht: `-IP <IP des Pi>`.
- Rückgängig: `-Uninstall` stellt die Original-Bibliothek wieder her.
- Firmware- und Bootloader-Befehle werden vom Pi immer abgelehnt.
- Es kann immer nur ein Central gleichzeitig verbunden sein.

Quellcode: `src/org/usb4java/` (Java 8). Bauen: `javac --release 8 -d build src/org/usb4java/*.java && jar cf usb4java-1.2.0.jar -C build .`
