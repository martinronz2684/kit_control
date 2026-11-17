# Kit Control 0.6 – Touch-Bedienung für den Sintratec Kit

Raspberry Pi 5 + Raspberry Pi Touch Display 2 (5") am Sintratec Kit.
Das Protokoll stammt aus dem Bytecode von Sintratec Central 1.2.0.
**Am echten Kit ist noch nichts getestet.** Die Tests laufen gegen einen nachgebauten Kit.

## Einrichten
1. **microSD-Karte** (32 GB) mit dem *Raspberry Pi Imager* beschreiben:
   Gerät *Raspberry Pi 5*, System *Raspberry Pi OS Lite (64-bit)*.
   In den Einstellungen Benutzer, Passwort, WLAN und **SSH** setzen.
2. **GitHub-Token** anlegen (einmalig): github.com → Settings → Developer settings →
   Personal access tokens → *Fine-grained tokens* → *Generate new token*.
   Repository access: *Only select repositories* → `kit_control`.
   Permissions: *Contents* → *Read-only*. Token kopieren.
3. Pi starten, per SSH anmelden und **einen Befehl** ausführen (`DEIN_TOKEN` zweimal ersetzen):
   ```bash
   curl -fsSL -H "Authorization: Bearer DEIN_TOKEN" -H "Accept: application/vnd.github.raw" \
     https://api.github.com/repos/martinronz2684/kit_control/contents/get.sh | sudo KIT_TOKEN=DEIN_TOKEN bash
   sudo reboot
   ```
4. **Aktualisieren** später: `sudo kit-update`

Danach startet der Pi still mit Logo und Ladebalken direkt in die Oberfläche. Die Oberfläche ist eine native Qt-App (`app/`), die ohne Desktop und ohne Browser direkt auf das Display zeichnet.
Ist das Display falsch herum eingebaut: in `/etc/kit/kitd.env` `KIT_ROTATION=270` setzen und `sudo systemctl restart kit-app`.

## WLAN
System → WLAN (oder das WLAN-Symbol oben): Netz antippen, Passwort über die Bildschirmtastatur eingeben, Verbinden.
Läuft über NetworkManager; das Land ist auf DE gesetzt (`KIT_WIFI_COUNTRY`).

## Erster Test am Kit
- **Central am PC trennen.** Am Kit darf immer nur ein Host hängen.
- Kit per USB an einen USB-A-Port des Pi.
- Auf dem Pi: `PYTHONPATH=/opt/kit-controller python3 -m kitctl.cli identify`
- Erst nur **anschauen**: Druck-Seite und System-Seite zeigen Modell, Firmware, Temperaturen.
- Dann **Bewegung mit 0,1 mm** testen. Fährt ▲ nach unten, in `/etc/kit/kitd.env`
  `KIT_MOVE_SIGN=-1` setzen und `sudo systemctl restart kitd`.
- Oberfläche ohne Kit ausprobieren: `KIT_DEMO=1` in `/etc/kit/kitd.env`.

## Aufbau
| Teil | Aufgabe |
|---|---|
| `kitctl/` | Protokoll und USB (pyusb), Befehle und Antworten |
| `kitd/` | Dienst: hält die USB-Verbindung, fragt jede Sekunde ab, nimmt Befehle an (`127.0.0.1:8080`) |
| `app/` | Native Oberfläche (Qt Quick/QML), 800×450 gezeichnet, auf dem 5"-Display gedreht und skaliert |
| `ui/` | Dieselbe Oberfläche als Webseite (später für Handy/PC im WLAN) |
| `system/` | systemd-Dienste, App-Start (Qt eglfs), Startbildschirm, udev-Regel |

## Sicherheit
- Firmware- und Bootloader-Befehle sind gesperrt. Central würde bei Modell 0 oder alter
  Firmware automatisch flashen – der Kit Controller bricht stattdessen ab.
- Fahren und Beschichten sind während des Drucks gesperrt, Fahrwege auf 120 mm begrenzt.
- Abbrechen, Sintern stoppen, Druck starten und Pulver laden fragen vorher nach.
- Bedienung über das Netz ist aus (nur am Gerät). `KIT_REMOTE=1` erlaubt sie.

## Noch offen
- PC-Durchreichen (Pi meldet sich am PC als Kit) – nächster Baustein
- Job-Bibliothek und Schichtansicht (braucht das Job-Dateiformat)
- Einige Codes stehen nicht in der Sintratec-Liste und werden als „unbekannt“ angezeigt

## Tests
```bash
python3 -m unittest -v
KIT_DEMO=1 PYTHONPATH=. python3 -m kitd.server   # dann http://127.0.0.1:8080
```

## Fehlersuche Oberfläche
`journalctl -u kit-app -b` zeigt Meldungen der App, `journalctl -u kitd -b` die des Dienstes.
