#!/bin/sh
# Startet die native Oberfläche mit dem QML-Laufzeitprogramm von Qt 6.
for q in /usr/lib/qt6/bin/qml /usr/lib/aarch64-linux-gnu/qt6/bin/qml "$(command -v qml6)" "$(command -v qml)"; do
  [ -n "$q" ] && [ -x "$q" ] && exec "$q" /opt/kit-controller/app/Main.qml -- --rotation "${KIT_ROTATION:-90}"
done
echo "Qt-QML-Laufzeit nicht gefunden (Paket qml-qt6)" >&2
exit 1
