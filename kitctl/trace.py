"""Mitschnitt aller USB-Transfers zum Kit (Ringpuffer) – für den Byte-Vergleich Central ↔ Kit Control.

Jeder Eintrag: Zeit, Quelle (Thread: „bridge“ = Central über den Pi, sonst kitd), Richtung, Länge, Bytes.
Datenrahmen der Dateiübertragung (512 Byte) werden nur gekürzt mit Prüfsumme festgehalten."""
from __future__ import annotations

import collections
import threading
import time
import zlib

_BUF: "collections.deque[tuple]" = collections.deque(maxlen=40000)
_LOCK = threading.Lock()


def add(direction: str, data: bytes, note: str = "") -> None:
    src = "central" if "bridge" in threading.current_thread().name.lower() or getattr(threading.current_thread(), "kit_bridge", False) else "kitd"
    with _LOCK:
        _BUF.append((time.time(), src, direction, bytes(data[:64]), len(data),
                     zlib.crc32(data) & 0xffffffff if len(data) > 64 else None, note))


def text(since: float = 0.0, only: str = "") -> str:
    out = []
    with _LOCK:
        rows = [r for r in _BUF if r[0] >= since and (not only or r[1] == only)]
    for t, src, d, head, n, crc, note in rows:
        lt = time.localtime(t)
        ts = time.strftime("%H:%M:%S", lt) + f".{int((t % 1) * 1000):03d}"
        code = head[0] | head[1] << 8 if len(head) >= 2 else -1
        extra = f" crc={crc:08x}" if crc is not None else ""
        out.append(f"{ts} {src:7s} {d} n={n:4d} code={code:5d} {head.hex()}{'…' if n > 64 else ''}{extra}{' ' + note if note else ''}")
    return "\n".join(out) + "\n"
