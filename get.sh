#!/bin/bash
# Kit Control installieren oder aktualisieren – holt den aktuellen Stand aus GitHub.
#
# Erstes Mal (Token einmal eingeben, er wird auf dem Pi gespeichert):
#   curl -fsSL -H "Authorization: Bearer DEIN_TOKEN" -H "Accept: application/vnd.github.raw" \
#     https://api.github.com/repos/martinronz2684/kit_control/contents/get.sh | sudo KIT_TOKEN=DEIN_TOKEN bash
#
# Danach jederzeit aktualisieren:
#   sudo kit-update
set -euo pipefail

REPO="${KIT_REPO:-martinronz2684/kit_control}"
BRANCH="${KIT_BRANCH:-main}"
TOKEN_FILE=/etc/kit/github-token

[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo starten."; exit 1; }
mkdir -p /etc/kit

if [ -n "${KIT_TOKEN:-}" ]; then
  umask 077
  printf '%s' "$KIT_TOKEN" > "$TOKEN_FILE"
fi
AUTH=()
if [ -s "$TOKEN_FILE" ]; then
  AUTH=(-H "Authorization: Bearer $(cat "$TOKEN_FILE")")
fi

# Nur nachsehen, welche Version im Repo liegt (für die Oberfläche)
if [ "${1:-}" = "--check" ]; then
  curl -fsSL "${AUTH[@]}" -H "Accept: application/vnd.github.sha" \
    "https://api.github.com/repos/$REPO/commits/$BRANCH" | cut -c1-7
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== Lade $REPO ($BRANCH)"
if ! curl -fsSL "${AUTH[@]}" -o "$WORK/src.tgz" "https://api.github.com/repos/$REPO/tarball/$BRANCH"; then
  echo "Download fehlgeschlagen. Token prüfen (Leserecht für Contents auf $REPO)."
  exit 1
fi
TOP="$(tar -tzf "$WORK/src.tgz" | head -n1)"
VERSION="${TOP%/}"; VERSION="${VERSION##*-}"
mkdir "$WORK/src"
tar -xzf "$WORK/src.tgz" -C "$WORK/src" --strip-components=1

bash "$WORK/src/install.sh"

# Update-Befehl einrichten, Version merken
install -m 755 "$WORK/src/get.sh" /usr/local/sbin/kit-update
printf '%s\n' "${VERSION:0:7}" > /etc/kit/version
echo "Version ${VERSION:0:7} installiert."

if systemctl is-active --quiet kit-app.service || [ -n "${INVOCATION_ID:-}" ]; then
  systemctl restart kitd.service kit-app.service
  echo "Dienste neu gestartet."
fi

echo
echo "Fertig. Beim ersten Mal mit 'sudo reboot' neu starten. Später aktualisieren: sudo kit-update"
