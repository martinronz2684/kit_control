#!/bin/sh
# Lädt die Oberfläche ohne Bildschirm (offscreen) und schlägt fehl, wenn QML nicht lädt.
# Läuft die App nach 8 s noch, gilt sie als in Ordnung. Laufzeitwarnungen werden mit ausgegeben.
set -u
Q=$(command -v qml6 || command -v qml || echo /usr/lib/qt6/bin/qml)
cd "$(dirname "$0")/../app"
QT_QPA_PLATFORM=offscreen timeout 8 "$Q" Main.qml -- --rotation 90 >/tmp/qml.log 2>&1
rc=$?
cat /tmp/qml.log
if [ $rc -ne 124 ]; then echo "FEHLER: Oberfläche startet nicht (Code $rc)"; exit 1; fi
if grep -Eq "is not a type|Cannot assign|Invalid property|Expected token|Syntax error|failed to load|Non-existent|is not installed|ReferenceError" /tmp/qml.log; then
  echo "FEHLER: QML-Fehler im Log"; exit 1
fi
echo "Oberfläche lädt."
