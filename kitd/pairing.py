"""Gekoppelte Geräte des Kit Control (PC-App, Handy, Central über WLAN).

Ein Gerät, das sich zum ersten Mal verbindet, fragt eine Kopplung an; am Display erscheint ein
6-stelliger Code, den man am Gerät eingibt (Ablauf und Kryptografie: kitctl/auth.py).
Gespeichert in <STATE_DIR>/pairings.json (nur für root/kitd lesbar):
  {"device_id": "...", "clients": {"<id>": {"name", "kind", "key", "created", "last_seen", "peer"}}}
Geräte entfernen geht nur am Display.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time

from kitctl import auth

REQUEST_TTL_S = 120          # so lange gilt ein Code
MAX_TRIES = 5                # falsche Codes je Anfrage
REJECT_COOLDOWN_S = 600      # nach „Ablehnen“ am Display: so lange keine neue Anfrage von dort
FAIL_COOLDOWN_S = 60         # nach zu vielen falschen Codes
KINDS = {"pc": "Kit Control", "phone": "Handy", "central": "Central"}
_QUERY_AUTH = re.compile(r"[?&]kc=")


class PairError(Exception):
    def __init__(self, msg: str, status: int = 403):
        super().__init__(msg)
        self.status = status


class Pairing:
    def __init__(self, state_dir: str):
        self.file = os.path.join(state_dir, "pairings.json")
        self.lock = threading.Lock()
        self.data = self._load()
        self.req = None                  # laufende Anfrage
        self.cooldown: dict[str, float] = {}
        self.nonces: dict[str, float] = {}
        self.done = None                 # zuletzt erfolgreich gekoppelt (für die Meldung am Display)
        self._seen_dirty = 0.0

    # -- Speicher -------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self.file) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError
        except (OSError, ValueError):
            d = {}
        d.setdefault("device_id", secrets.token_hex(8))
        if not isinstance(d.get("clients"), dict):
            d["clients"] = {}
        if not os.path.exists(self.file):
            self._write(d)
        return d

    def _write(self, d: dict | None = None) -> None:
        d = d if d is not None else self.data
        try:
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
            tmp = self.file + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(d, f, indent=1)
            os.replace(tmp, self.file)
        except OSError as e:
            print(f"Kopplung: speichern fehlgeschlagen: {e}", flush=True)

    @property
    def device_id(self) -> str:
        return self.data["device_id"]

    # -- Koppeln --------------------------------------------------------------
    def start(self, name: str, kind: str, peer: str, a_hex: str, busy: str = "") -> dict:
        """Neue Anfrage: zeigt einen Code am Display. Antwort {"request_id", "B", "device_id", "expires_in"}."""
        now = time.time()
        name = re.sub(r"[\x00-\x1f]", "", str(name or "")).strip()[:40] or "Unbekanntes Gerät"
        kind = kind if kind in KINDS else "pc"
        if busy:
            raise PairError(busy, 409)
        try:
            a_pub = int(str(a_hex), 16)
        except ValueError:
            raise PairError("ungültige Anfrage", 400) from None
        if not auth.valid_public(a_pub):
            raise PairError("ungültige Anfrage", 400)
        with self.lock:
            until = self.cooldown.get(peer, 0)
            if until > now:
                raise PairError(f"Kopplung von diesem Gerät gesperrt – in {int(until - now) // 60 + 1} min erneut versuchen", 429)
            r = self.req
            if r and r["expires"] > now and r["peer"] != peer:
                raise PairError("Am Kit wartet schon eine andere Kopplung – bitte kurz warten", 409)
            b, b_pub = auth.keypair()
            code = auth.new_code()
            self.req = {"id": secrets.token_hex(8), "name": name, "kind": kind, "peer": peer, "code": code,
                        "a": a_pub, "b_pub": b_pub, "key": auth.derive(code, a_pub, b_pub, auth.shared_secret(b, a_pub)),
                        "created": now, "expires": now + REQUEST_TTL_S, "tries": 0}
            print(f"Kopplung angefragt: {name} ({KINDS[kind]}, {peer})", flush=True)
            return {"request_id": self.req["id"], "B": format(b_pub, "x"), "device_id": self.device_id,
                    "expires_in": REQUEST_TTL_S}

    def confirm(self, request_id: str, mac_hex: str, peer: str) -> dict:
        now = time.time()
        with self.lock:
            r = self.req
            if not r or r["id"] != request_id or r["expires"] < now:
                raise PairError("Die Kopplung ist abgelaufen oder wurde am Kit abgelehnt – bitte neu starten", 410)
            if r["peer"] != peer:
                raise PairError("Anfrage gehört zu einem anderen Gerät", 403)
            if not secrets.compare_digest(auth.mac(r["key"], "client", request_id), str(mac_hex)):
                r["tries"] += 1
                if r["tries"] >= MAX_TRIES:
                    self.req = None
                    self.cooldown[peer] = now + FAIL_COOLDOWN_S
                    raise PairError("Zu oft falsch – Kopplung abgebrochen. In einer Minute neu versuchen", 429)
                raise PairError(f"Code falsch – noch {MAX_TRIES - r['tries']} Versuch(e)", 401)
            cid = secrets.token_hex(8)
            self.data["clients"][cid] = {"name": r["name"], "kind": r["kind"], "key": r["key"].hex(),
                                         "created": int(now), "last_seen": int(now), "peer": peer}
            self._write()
            self.req = None
            self.done = {"name": r["name"], "kind": r["kind"], "ts": now}
            print(f"Gekoppelt: {r['name']} ({KINDS[r['kind']]}, {peer})", flush=True)
            return {"client_id": cid, "mac": auth.mac(bytes.fromhex(self.data["clients"][cid]["key"]), "server", cid),
                    "device_id": self.device_id}

    def cancel(self) -> bool:
        """„Ablehnen“ am Display: Anfrage verwerfen, Gerät eine Weile sperren."""
        with self.lock:
            r, self.req = self.req, None
            if r:
                self.cooldown[r["peer"]] = time.time() + REJECT_COOLDOWN_S
            return r is not None

    def abort_if_busy(self) -> None:
        """Beginnt ein Druck oder das Vorheizen, verfällt eine offene Anfrage."""
        with self.lock:
            self.req = None

    def pending(self) -> dict | None:
        """Laufende Anfrage für das Display (mit Code) – nie an Geräte im Netz geben."""
        with self.lock:
            r = self.req
            if not r:
                return None
            left = r["expires"] - time.time()
            if left <= 0:
                self.req = None
                return None
            return {"name": r["name"], "kind": r["kind"], "kind_name": KINDS[r["kind"]], "peer": r["peer"],
                    "code": r["code"], "expires_in": int(left), "tries": r["tries"]}

    # -- Verwaltung -----------------------------------------------------------
    def clients(self) -> list[dict]:
        with self.lock:
            out = [{"id": cid, "name": c.get("name", ""), "kind": c.get("kind", "pc"),
                    "kind_name": KINDS.get(c.get("kind", "pc"), "Gerät"), "created": c.get("created", 0),
                    "last_seen": c.get("last_seen", 0), "peer": c.get("peer", "")}
                   for cid, c in self.data["clients"].items()]
        return sorted(out, key=lambda c: -c["last_seen"])

    def remove(self, cid: str) -> bool:
        with self.lock:
            if self.data["clients"].pop(str(cid), None) is None:
                return False
            self._write()
            return True

    def key(self, cid: str) -> bytes | None:
        c = self.data["clients"].get(str(cid))
        return bytes.fromhex(c["key"]) if c else None

    def seen(self, cid: str, peer: str) -> None:
        c = self.data["clients"].get(cid)
        if not c:
            return
        now = time.time()
        c["last_seen"], c["peer"] = int(now), peer
        if now - self._seen_dirty > 600:        # „zuletzt gesehen“ höchstens alle 10 min auf die SD-Karte
            self._seen_dirty = now
            with self.lock:
                self._write()

    # -- Unterschrift prüfen --------------------------------------------------
    def verify(self, method: str, path: str, headers, body: bytes | None, peer: str = "") -> str | None:
        """Geräte-Nummer, wenn die Anfrage gültig unterschrieben ist, sonst None."""
        m = _QUERY_AUTH.search(path)
        if m:
            from urllib.parse import parse_qs
            q = {k: v[0] for k, v in parse_qs(path[m.start() + 1:].split("?")[-1]).items()}
            signed = path[:m.start()]
            cid, ts, nonce, sig = q.get("kc", ""), q.get("kt", ""), q.get("kn", ""), q.get("ks", "")
        else:
            signed = path
            cid, ts, nonce, sig = (headers.get(h, "") or "" for h in ("X-Kit-Client", "X-Kit-Time", "X-Kit-Nonce", "X-Kit-Sig"))
        if not (cid and ts and nonce and sig) or not 8 <= len(nonce) <= 64:
            return None
        key = self.key(cid)
        if key is None:
            return None
        try:
            if abs(float(ts) - time.time()) > auth.TIME_WINDOW_S:
                return None
        except ValueError:
            return None
        want = auth.sign(key, method, signed, ts, nonce, auth.body_hash(body), auth.signed_headers(headers.get))
        if not secrets.compare_digest(want, str(sig)):
            return None
        now = time.time()
        with self.lock:
            if len(self.nonces) > 5000:
                self.nonces = {n: t for n, t in self.nonces.items() if t > now}
            tag = cid + ":" + nonce
            if tag in self.nonces:
                return None                      # Wiederholung einer mitgeschnittenen Anfrage
            self.nonces[tag] = now + 2 * auth.TIME_WINDOW_S
        self.seen(cid, peer)
        return cid
