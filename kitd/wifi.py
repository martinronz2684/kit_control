"""WLAN über NetworkManager (nmcli). Im Demo-Modus werden Netze simuliert."""
from __future__ import annotations

import os
import subprocess

DEMO = os.environ.get("KIT_DEMO") == "1"
_demo = {"current": "Werkstatt"}


def _split(line: str) -> list[str]:
    """nmcli -t trennt mit ':' und maskiert ':' im Wert als '\\:'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _nmcli(*args: str, timeout: float = 20) -> str:
    # LC_ALL=C: sonst liefert nmcli auf deutschem System "ja"/"nein" statt "yes"/"no"
    env = dict(os.environ, LC_ALL="C", LANG="C")
    r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "nmcli-Fehler")
    return r.stdout


def status(rescan: bool = False) -> dict:
    if DEMO:
        nets = [("Werkstatt", 82, True), ("FRITZ!Box 7590 KL", 64, True), ("Gast", 41, False), ("DIRECT-HP-Drucker", 22, True)]
        return {"available": True, "current": _demo["current"], "ip": "192.168.1.48" if _demo["current"] else "",
                "networks": [{"ssid": n, "signal": s, "secure": sec, "active": n == _demo["current"]} for n, s, sec in nets]}
    try:
        rows = _nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                      "--rescan", "yes" if rescan else "auto")
    except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"available": False, "error": str(e), "networks": []}
    best: dict[str, dict] = {}
    for line in rows.splitlines():
        f = _split(line)
        if len(f) < 4 or not f[1]:
            continue
        n = {"ssid": f[1], "signal": int(f[2] or 0), "secure": f[3] not in ("", "--"), "active": f[0] in ("yes", "ja", "*")}
        old = best.get(n["ssid"])
        if not old or n["active"] or n["signal"] > old["signal"] and not old["active"]:
            best[n["ssid"]] = n
    nets = sorted(best.values(), key=lambda n: (not n["active"], -n["signal"]))
    current = next((n["ssid"] for n in nets if n["active"]), "")
    ip = ""
    try:
        for line in _nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0").splitlines():
            if ":" in line:
                ip = line.split(":", 1)[1].split("/")[0]
                break
    except Exception:
        pass
    return {"available": True, "current": current, "ip": ip, "networks": nets}


def _security_of(ssid: str) -> str:
    """SECURITY-Feld aus dem letzten Scan, z. B. 'WPA2', 'WPA2 WPA3', 'WPA3' oder ''."""
    try:
        for line in _nmcli("-t", "-f", "SSID,SECURITY", "dev", "wifi", "list", "--rescan", "no").splitlines():
            f = _split(line)
            if len(f) >= 2 and f[0] == ssid:
                return f[1]
    except Exception:
        pass
    return ""


def connect(ssid: str, password: str = "") -> None:
    if not ssid or len(ssid) > 32 or (password and not 8 <= len(password) <= 63):
        raise ValueError("WLAN-Passwort muss 8–63 Zeichen haben")
    if DEMO:
        if password == "falsch123":
            raise ValueError("Verbindung fehlgeschlagen: Passwort falsch?")
        _demo["current"] = ssid
        return
    # Profil immer selbst anlegen: "nmcli dev wifi connect" scheitert auf dem Pi oft mit
    # "802-11-wireless-security.key-mgmt: Eigenschaft fehlt".
    # Mehrere Versuche, weil der WLAN-Chip des Pi mit gemischten WPA2/WPA3-Netzen
    # oft nur ohne Management-Frame-Schutz (PMF) oder nur mit SAE zurechtkommt.
    name = f"kit-{ssid}"
    sec = _security_of(ssid).upper() if password else ""
    if not password:
        attempts = [[]]
    elif "WPA3" in sec and "WPA2" not in sec and "WPA1" not in sec:
        attempts = [["wifi-sec.key-mgmt", "sae"], ["wifi-sec.key-mgmt", "sae", "wifi-sec.pmf", "3"]]
    else:
        attempts = [["wifi-sec.key-mgmt", "wpa-psk"],
                    ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.pmf", "1"]]
        if "WPA3" in sec:
            attempts.append(["wifi-sec.key-mgmt", "sae"])
    reason = ""
    for extra in attempts:
        try:
            _nmcli("connection", "delete", "id", name, timeout=15)
        except Exception:
            pass
        args = ["connection", "add", "type", "wifi", "ifname", "wlan0", "con-name", name,
                "ssid", ssid, "connection.autoconnect", "yes"] + extra
        if password:
            args += ["wifi-sec.psk", password]
        try:
            _nmcli(*args, timeout=20)
            _nmcli("connection", "up", "id", name, timeout=45)
            return
        except (RuntimeError, subprocess.TimeoutExpired):
            reason = _last_reason() or reason
    try:
        _nmcli("connection", "delete", "id", name, timeout=15)
    except Exception:
        pass
    text = {
        "no-secrets": "Passwort falsch?",
        "supplicant-disconnect": "Passwort falsch oder Verschlüsselung nicht unterstützt",
        "supplicant-timeout": "Router antwortet nicht – Passwort falsch?",
        "ssid-not-found": "Netz nicht gefunden – näher an den Router?",
        "supplicant-failed": "WLAN-Dienst gestört",
    }.get(reason, f"Grund: {reason}" if reason else "unbekannter Grund")
    raise ValueError(f"Verbindung fehlgeschlagen: {text}")


def _last_reason() -> str:
    """Letzten Abbruchgrund aus dem Protokoll von NetworkManager lesen."""
    try:
        out = subprocess.run(["journalctl", "-u", "NetworkManager", "-n", "60", "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""
    import re
    found = re.findall(r"reason '([a-z-]+)'", out)
    for r in reversed(found):
        if r not in ("none", "user-requested", "connection-removed", "new-activation", "unknown", "managed"):
            return r
    return ""


def disconnect() -> None:
    if DEMO:
        _demo["current"] = ""
        return
    try:
        _nmcli("dev", "disconnect", "wlan0")
    except RuntimeError as e:
        raise ValueError(str(e)) from e
