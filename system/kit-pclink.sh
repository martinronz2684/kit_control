#!/bin/bash
# PC-Verbindung für Central umschalten: wlan (Standard) oder usb.
# usb: Der USB-C-Anschluss des Pi wird zum Netzwerkadapter am PC (RNDIS).
#      Der Pi hat dort 10.55.0.1 und vergibt dem PC per DHCP eine Adresse.
# Aufruf: kit-pclink.sh wlan|usb|apply
set -u
MODE_FILE=/etc/kit/pc-link
G=/sys/kernel/config/usb_gadget/kit

mode="${1:-apply}"
if [ "$mode" = apply ]; then
  mode="$(cat "$MODE_FILE" 2>/dev/null || echo wlan)"
fi
case "$mode" in wlan|usb) ;; *) echo "wlan oder usb"; exit 2 ;; esac

gadget_off() {
  [ -d "$G" ] || return 0
  echo "" > "$G/UDC" 2>/dev/null || true
  rm -f "$G/os_desc/c.1" "$G/configs/c.1/rndis.usb0" 2>/dev/null
  rmdir "$G/configs/c.1/strings/0x409" "$G/configs/c.1" "$G/functions/rndis.usb0" "$G/strings/0x409" "$G" 2>/dev/null || true
}

gadget_on() {
  modprobe libcomposite || return 1
  [ -d "$G" ] && gadget_off
  mkdir -p "$G" && cd "$G" || return 1
  echo 0x1d6b > idVendor          # Linux Foundation
  echo 0x0104 > idProduct         # Multifunction Composite Gadget
  echo 0x0100 > bcdDevice
  echo 0x0200 > bcdUSB
  echo 0xEF > bDeviceClass; echo 0x02 > bDeviceSubClass; echo 0x01 > bDeviceProtocol
  mkdir -p strings/0x409
  echo "$(tr -d '\0' < /proc/device-tree/serial-number 2>/dev/null || echo 0001)" > strings/0x409/serialnumber
  echo "Kit Control" > strings/0x409/manufacturer
  echo "Kit Control USB" > strings/0x409/product
  mkdir -p configs/c.1/strings/0x409
  echo "Netzwerk" > configs/c.1/strings/0x409/configuration
  echo 250 > configs/c.1/MaxPower
  # Windows erkennt RNDIS ohne Treiber über die Microsoft-OS-Deskriptoren
  echo 1 > os_desc/use; echo 0xcd > os_desc/b_vendor_code; echo MSFT100 > os_desc/qw_sign
  mkdir -p functions/rndis.usb0
  echo RNDIS > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
  echo 5162001 > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id
  ln -s functions/rndis.usb0 configs/c.1/
  ln -s configs/c.1 os_desc/
  UDC="$(ls /sys/class/udc | head -n1)"
  [ -n "$UDC" ] || { echo "Kein USB-Gerätemodus (dtoverlay=dwc2 fehlt oder Neustart nötig)"; return 1; }
  echo "$UDC" > UDC
}

net_on() {
  nmcli connection delete id kit-usb >/dev/null 2>&1 || true
  for i in $(seq 1 20); do ip link show usb0 >/dev/null 2>&1 && break; sleep 0.5; done
  nmcli connection add type ethernet ifname usb0 con-name kit-usb autoconnect yes \
    ipv4.method shared ipv4.addresses 10.55.0.1/24 ipv6.method disabled >/dev/null
  nmcli connection up id kit-usb >/dev/null 2>&1 || true
}

net_off() { nmcli connection delete id kit-usb >/dev/null 2>&1 || true; }

if [ "$mode" = usb ]; then
  if gadget_on; then net_on; else echo wlan > "$MODE_FILE"; exit 1; fi
else
  net_off; gadget_off
fi
echo "$mode" > "$MODE_FILE"
echo "PC-Verbindung: $mode"
