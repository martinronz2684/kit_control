#!/bin/sh
# Startet die native Oberfläche mit dem QML-Laufzeitprogramm von Qt 6.
# Stürzt eine neue Oberfläche sofort ab, startet die vorige Version (app.prev),
# damit System → Software immer erreichbar bleibt.
Q=""
for q in /usr/lib/qt6/bin/qml /usr/lib/aarch64-linux-gnu/qt6/bin/qml "$(command -v qml6)" "$(command -v qml)"; do
  [ -n "$q" ] && [ -x "$q" ] && { Q="$q"; break; }
done
[ -n "$Q" ] || { echo "Qt-QML-Laufzeit nicht gefunden (Paket qml-qt6)" >&2; exit 1; }
ROT="${KIT_ROTATION:-90}"
D=/opt/kit-controller
start=$(date +%s)
"$Q" "$D/app/Main.qml" -- --rotation "$ROT"
rc=$?
if [ $rc -ne 0 ] && [ $(( $(date +%s) - start )) -lt 20 ] && [ -f "$D/app.prev/Main.qml" ]; then
  echo "Neue Oberfläche startet nicht (Code $rc) – nehme vorige Version" >&2
  exec "$Q" "$D/app.prev/Main.qml" -- --rotation "$ROT"
fi
exit $rc
