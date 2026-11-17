#!/bin/bash
# Kit Controller einrichten – auf frischem Raspberry Pi OS Lite (64-bit, Trixie) als root:
#   sudo ./install.sh
# Danach: sudo reboot
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo starten: sudo ./install.sh"; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
DST=/opt/kit-controller
BOOT=/boot/firmware
ROTATION="${KIT_ROTATION:-90}"   # 90 oder 270, je nachdem wie das Display eingebaut ist

echo "== Pakete"
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-usb network-manager \
  plymouth plymouth-themes fonts-inter fonts-dejavu-core \
  qml-qt6 qml6-module-qtquick qml6-module-qtquick-window qml6-module-qtqml-workerscript
# Qt-Plattform für die direkte Ausgabe aufs Display (Paketname je nach Qt-Version)
for p in qt6-qpa-plugins libqt6opengl6 qml6-module-qtqml-models; do apt-get install -y --no-install-recommends "$p" || true; done

echo "== Benutzer kit"
id kit >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin kit
usermod -aG plugdev,video,render,input,systemd-journal kit

echo "== Programm nach $DST"
rm -rf "$DST"
mkdir -p "$DST"
cp -r "$SRC/kitctl" "$SRC/kitd" "$SRC/ui" "$SRC/app" "$SRC/branding" "$SRC/system" "$DST/"
chmod +x "$DST/system/kit-app.sh"
mkdir -p /etc/kit
[ -f /etc/kit/kitd.env ] || cat > /etc/kit/kitd.env <<EOF
# KIT_DEMO=1 simuliert einen Kit (Oberfläche ohne Hardware testen)
# KIT_MOVE_SIGN=-1 dreht die Fahrrichtung um, falls ▲/▼ vertauscht sind
KIT_ROTATION=$ROTATION
EOF

echo "== USB-Rechte für den Kit"
cp "$SRC/system/99-sintratec-kit.rules" /etc/udev/rules.d/
udevadm control --reload 2>/dev/null || true

echo "== WLAN aus der Oberfläche einrichten erlauben"
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-kit-wifi.rules <<'RULE'
polkit.addRule(function (action, subject) {
  if (subject.user == "kit" && action.id.indexOf("org.freedesktop.NetworkManager.") == 0) {
    return polkit.Result.YES;
  }
});
RULE
raspi-config nonint do_wifi_country "${KIT_WIFI_COUNTRY:-DE}" 2>/dev/null || true
rfkill unblock wifi 2>/dev/null || true

echo "== Neustart/Ausschalten aus der Oberfläche erlauben"
cat > /etc/sudoers.d/kit-controller <<'EOF'
kit ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff, /usr/bin/systemctl start --no-block kit-update.service, /usr/local/sbin/kit-update --check
EOF
chmod 440 /etc/sudoers.d/kit-controller

echo "== Dienste"
systemctl disable --now kit-kiosk.service 2>/dev/null || true
rm -f /etc/systemd/system/kit-kiosk.service
cp "$SRC/system/kitd.service" "$SRC/system/kit-app.service" "$SRC/system/kit-update.service" /etc/systemd/system/
systemctl daemon-reload 2>/dev/null || true
systemctl enable kitd.service kit-app.service
systemctl set-default multi-user.target
systemctl disable getty@tty1.service || true
systemctl disable NetworkManager-wait-online.service 2>/dev/null || true

echo "== Startbildschirm"
THEME=/usr/share/plymouth/themes/kit
mkdir -p "$THEME"
cp "$SRC/system/plymouth/"* "$THEME/"
if [ -f /etc/kit/logo.png ]; then cp /etc/kit/logo.png "$THEME/logo.png"; fi
plymouth-set-default-theme kit

echo "== config.txt (Display, kein Regenbogen)"
CFG="$BOOT/config.txt"
cp -n "$CFG" "$CFG.vor-kit" || true
grep -q '^# kit-controller' "$CFG" || cat >> "$CFG" <<'EOF'

# kit-controller
[all]
disable_splash=1
dtoverlay=vc4-kms-dsi-ili9881-5inch
EOF

echo "== cmdline.txt (stiller Boot)"
CMD="$BOOT/cmdline.txt"
cp -n "$CMD" "$CMD.vor-kit" || true
LINE="$(head -n1 "$CMD")"
for opt in quiet splash loglevel=0 logo.nologo vt.global_cursor_default=0 plymouth.ignore-serial-consoles \
           "video=DSI-1:720x1280@60,rotate=$ROTATION" "video=DSI-2:720x1280@60,rotate=$ROTATION"; do
  case " $LINE " in *" $opt "*) ;; *) LINE="$LINE $opt" ;; esac
done
LINE="${LINE//console=tty1/console=tty3}"
echo "$LINE" > "$CMD"

echo "== initramfs (für den Startbildschirm)"
update-initramfs -u || echo "Hinweis: initramfs nicht aktualisiert"

echo
echo "Fertig. Logo: weißes PNG mit transparentem Hintergrund nach /etc/kit/logo.png kopieren"
echo "und dieses Skript noch einmal starten. Jetzt: sudo reboot"
