"""Kopplung und Anfrage-Unterschrift zwischen Kit Control am Pi und PC, Handy, Central.

Koppeln (einmalig):
  1. Gerät -> Pi: Name und öffentlicher Diffie-Hellman-Wert A (RFC 3526, Gruppe 14, 2048 Bit, g = 2).
  2. Pi zeigt einen zufälligen 6-stelligen Code am Display und antwortet mit B und einer Anfrage-Nummer.
  3. Beide berechnen  K = HMAC-SHA256(Schlüssel = Code, "kitpair1" | A | B | g^ab)  (je 256 Byte, Big Endian).
     Wer nur mithört, kennt g^ab nicht; wer den Code nicht kennt, kommt nicht auf K.
  4. Gerät -> Pi: HMAC(K, "client|" + Anfrage-Nummer). Stimmt sie, merkt sich der Pi K unter einer neuen
     Geräte-Nummer und beweist mit HMAC(K, "server|" + Geräte-Nummer), dass er K ebenfalls kennt.
  K selbst geht nie über das Netz.

Danach (jede Anfrage):
  Unterschrift = HMAC-SHA256(K, Methode \\n Pfad \\n Zeit \\n Einmalnummer \\n SHA-256(Rumpf)
                 [\\n X-Job-Name:… \\n X-Job-Profile:… \\n X-Job-Start:…  – nur beim Job-Upload])  als Hex.
  Mitgeschickt als Kopfzeilen X-Kit-Client, X-Kit-Time, X-Kit-Nonce, X-Kit-Sig – oder, wo keine
  Kopfzeilen gehen (EventSource im Browser), als letzte Parameter kc, kt, kn, ks an der Adresse;
  unterschrieben ist dann die Adresse ohne diese Parameter. Die Zeit gilt ±5 min nach der Uhr des Pi
  (das Gerät gleicht seine Uhr über /api/pair/hello ab), jede Einmalnummer nur einmal.

Nur Standardbibliothek – läuft auf dem Pi und in der PC-App.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# RFC 3526, 2048-bit MODP Group 14
P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
G = 2
PROTO = "kitpair1"
CODE_DIGITS = 6
TIME_WINDOW_S = 300


def i2b(x: int) -> bytes:
    return x.to_bytes(256, "big")


def keypair() -> tuple[int, int]:
    """(geheim, öffentlich)"""
    a = secrets.randbits(256) | (1 << 255)
    return a, pow(G, a, P)


def valid_public(x: int) -> bool:
    return 2 <= x <= P - 2


def shared_secret(priv: int, other_pub: int) -> int:
    if not valid_public(other_pub):
        raise ValueError("ungültiger öffentlicher Wert")
    return pow(other_pub, priv, P)


def derive(code: str, a_pub: int, b_pub: int, shared: int) -> bytes:
    return hmac.new(code.encode(), PROTO.encode() + i2b(a_pub) + i2b(b_pub) + i2b(shared), hashlib.sha256).digest()


def mac(key: bytes, label: str, text: str) -> str:
    return hmac.new(key, f"{label}|{text}".encode(), hashlib.sha256).hexdigest()


def body_hash(body: bytes | None) -> str:
    return hashlib.sha256(body or b"").hexdigest()


SIGNED_HEADERS = ("X-Job-Name", "X-Job-Profile", "X-Job-Start")


def signed_headers(get) -> str:
    """Kopfzeilen, die mit unterschrieben werden (Job-Upload); leer, wenn keine davon vorkommt."""
    vals = [get(h) or "" for h in SIGNED_HEADERS]
    return "\n".join(f"{h}:{v}" for h, v in zip(SIGNED_HEADERS, vals)) if any(vals) else ""


def sign(key: bytes, method: str, path: str, ts: str, nonce: str, bhash: str, extra: str = "") -> str:
    msg = f"{method.upper()}\n{path}\n{ts}\n{nonce}\n{bhash}"
    if extra:
        msg += "\n" + extra
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def new_nonce() -> str:
    return secrets.token_hex(12)
