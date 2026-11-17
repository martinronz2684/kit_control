"""Central über WLAN: reicht USB-Transfers von Sintratec Central an den Kit weiter.

Auf dem PC ersetzt central/usb4java-1.2.0.jar die USB-Bibliothek von Central und schickt
jeden Bulk-Transfer hierher. kitd führt ihn auf dem echten Kit aus – unter derselben
Sperre wie seine eigenen Abfragen. Ein Schreibvorgang und die folgende Antwort laufen
zusammen, damit sich Central und das Display nicht ins Wort fallen.

Protokoll (TCP, Big Endian):
  Anfrage: op(1) ep(1) timeout_ms(4) len(4) daten(len)
  Antwort: status(4, signed; libusb-Codes) len(4) daten(len)
  op: 'H' Hallo/Kit da?  'W' schreiben  'R' lesen (len = maximale Länge)

Daneben beantwortet ein UDP-Dienst die Suche "KITCONTROL?" mit "KITCONTROL <port> <name>".
"""
from __future__ import annotations

import ipaddress
import os
import socket
import socketserver
import struct
import threading
import time

from kitctl import protocol as P

PORT = int(os.environ.get("KIT_BRIDGE_PORT", "8766"))
DISCOVERY_PORT = 8767
HOLD_MAX = 5.0          # so lange darf Central die Sperre zwischen Schreiben und Lesen halten

OK, ERR_IO, ERR_NO_DEVICE, ERR_TIMEOUT, ERR_ACCESS = 0, -1, -4, -7, -3

# Firmware/Bootloader nie über die Brücke: Bootloader laden, Flash-Anfrage, FPJ16-Flashpakete
BLOCKED = set(P.FORBIDDEN) | set(range(6000, 6100))

_session_lock = threading.Lock()
STATE = {"central": False, "peer": "", "since": 0.0, "transfers": 0}


def _allowed(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _recv(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("getrennt")
        buf += chunk
    return buf


class Session(socketserver.BaseRequestHandler):
    worker = None  # gesetzt in start_bridge
    pending = None

    def reply(self, status: int, data: bytes = b"") -> None:
        self.request.sendall(struct.pack(">iI", status, len(data)) + data)

    def handle(self):
        peer = self.client_address[0]
        if not _allowed(peer):
            return
        # Eine reine Anfrage "Kit da?" (Gerätesuche von Central) braucht keine Sitzung.
        self.request.settimeout(5.0)
        try:
            first = _recv(self.request, 10)
        except (OSError, ConnectionError):
            return
        if first[:1] == b"H":
            self.reply(OK if self.worker.kit is not None else ERR_NO_DEVICE)
            return
        self.pending = first
        if not _session_lock.acquire(blocking=False):
            # Es darf nur ein Central gleichzeitig verbunden sein.
            try:
                self.reply(ERR_ACCESS)
            except OSError:
                pass
            return
        held = False
        held_since = 0.0
        usb = self.worker.usb
        sock = self.request
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(1.0)
        STATE.update(central=True, peer=peer, since=time.time())
        try:
            while True:
                try:
                    if self.pending:
                        head, self.pending = self.pending, None
                    else:
                        head = _recv(sock, 10)
                except socket.timeout:
                    if held and time.time() - held_since > HOLD_MAX:
                        usb.release(); held = False
                    continue
                op, ep, timeout_ms, n = struct.unpack(">cBII", head)
                sock.settimeout(10.0)
                data = _recv(sock, n) if op == b"W" else b""
                sock.settimeout(1.0)
                kit = self.worker.kit

                if op == b"H":
                    self.reply(OK if kit is not None else ERR_NO_DEVICE)
                    continue
                if kit is None:
                    if held:
                        usb.release(); held = False
                    self.reply(ERR_NO_DEVICE)
                    continue
                if op == b"W":
                    if len(data) >= 2 and P.code_of(data) in BLOCKED:
                        self.reply(ERR_ACCESS)
                        continue
                    if not held:
                        if not usb.acquire(timeout=HOLD_MAX):
                            self.reply(ERR_TIMEOUT); continue
                        held, held_since = True, time.time()
                    try:
                        kit.t.write(data)
                        self.reply(OK, struct.pack(">I", len(data)))
                    except Exception:
                        usb.release(); held = False
                        self.reply(ERR_IO)
                elif op == b"R":
                    if not held:
                        if not usb.acquire(timeout=HOLD_MAX):
                            self.reply(ERR_TIMEOUT); continue
                        held = True
                    try:
                        ans = kit.t.read(n)[:n]
                        self.reply(OK, ans)
                    except Exception as e:
                        self.reply(ERR_TIMEOUT if "timeout" in str(e).lower() or "timed out" in str(e).lower() else ERR_IO)
                    finally:
                        usb.release(); held = False
                else:
                    self.reply(ERR_IO)
                STATE["transfers"] += 1
        except (ConnectionError, OSError):
            pass
        finally:
            if held:
                usb.release()
            STATE.update(central=False, peer="")
            _session_lock.release()


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _discovery():
    name = socket.gethostname()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", DISCOVERY_PORT))
    while True:
        try:
            msg, addr = s.recvfrom(256)
            if msg.strip() == b"KITCONTROL?" and _allowed(addr[0]):
                s.sendto(f"KITCONTROL {PORT} {name}".encode(), addr)
        except OSError:
            time.sleep(1)


def start_bridge(worker) -> None:
    Session.worker = worker
    srv = _Server(("0.0.0.0", PORT), Session)
    threading.Thread(target=srv.serve_forever, daemon=True, name="central-bridge").start()
    threading.Thread(target=_discovery, daemon=True, name="central-discovery").start()
