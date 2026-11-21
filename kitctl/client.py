"""Talking to the Kit over USB (pyusb / libusb).

Only read-only requests are exposed for now. Flashing codes are blocked.
"""
from __future__ import annotations

from typing import Protocol

from . import protocol as P


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, size: int) -> bytes: ...
    def close(self) -> None: ...


class UsbTransport:
    """Bulk OUT 0x06 / bulk IN 0x85 on interface 0, like Central does."""

    def __init__(self, timeout_ms: int = P.TIMEOUT_MS):
        try:
            import usb.core
            import usb.util
        except ImportError as e:  # pragma: no cover
            raise SystemExit("pyusb fehlt: sudo apt install python3-usb") from e
        self._usb = usb
        dev = usb.core.find(idVendor=P.VENDOR_ID, idProduct=P.PRODUCT_ID)
        if dev is None:
            raise SystemExit("Kein Kit gefunden (USB 03eb:8002). Kabel und Strom prüfen.")
        self.dev = dev
        self.timeout = timeout_ms
        self._reattach = False
        try:
            if dev.is_kernel_driver_active(P.INTERFACE):
                dev.detach_kernel_driver(P.INTERFACE)
                self._reattach = True
        except (NotImplementedError, usb.core.USBError):
            pass
        usb.util.claim_interface(dev, P.INTERFACE)

    def write(self, data: bytes) -> None:
        n = self.dev.write(P.EP_OUT, data, timeout=self.timeout)
        if n != len(data):
            raise P.ProtocolError(f"nur {n} von {len(data)} Bytes gesendet")

    def read(self, size: int) -> bytes:
        return bytes(self.dev.read(P.EP_IN, max(size, P.BULK_BUFFER), timeout=self.timeout))

    def close(self) -> None:
        u = self._usb.util
        try:
            u.release_interface(self.dev, P.INTERFACE)
            if self._reattach:
                self.dev.attach_kernel_driver(P.INTERFACE)
        finally:
            u.dispose_resources(self.dev)


class Kit:
    def __init__(self, transport: Transport):
        self.t = transport
        self.identity: P.Identity | None = None

    # low level ---------------------------------------------------------------
    def transact(self, payload: bytes, answer_len: int) -> bytes:
        c = P.code_of(payload)
        if c in P.FORBIDDEN:
            raise P.ProtocolError(f"Code {c} (Firmware/Bootloader) wird nie gesendet")
        self.t.write(payload)
        ans = self.t.read(answer_len)
        if len(ans) < 2:
            raise P.ProtocolError("leere Antwort")
        return ans

    # handshake -------------------------------------------------------------
    def identify(self) -> P.Identity:
        ans = self.transact(P.code(P.COM_IDENTIFY), P.Identity.LENGTH)
        self.identity = P.Identity.parse(ans)
        return self.identity

    def connect(self) -> P.Identity:
        """IDENTIFY, check model, then CONNECTION_ESTABLISHED (as Central does).

        Central would flash the recovery bootloader if model == 0 or the firmware
        is older than 12. We never do that: we stop and report instead.
        """
        ident = self.identify()
        if ident.model == 0:
            raise P.ProtocolError("Kit meldet Recovery-Bootloader (Modell 0). Abbruch, kein Flashen.")
        if not ident.is_supported_kit:
            raise P.ProtocolError(
                f"Unerwartetes Gerät: Modell {ident.model}, Protokoll {ident.comm}, "
                f"Firmware {ident.firmware} (erwartet Kit 2/4, Protokoll 4, Firmware 12)")
        ans = self.transact(P.code(P.COM_CONNECTION_ESTABLISHED), 3)
        if P.code_of(ans) != P.SIG_OPERATION_SUCCESSFUL:
            raise P.ProtocolError(f"Verbindungsbestätigung fehlt (Antwort {P.code_of(ans)})")
        return ident

    # read-only requests ------------------------------------------------------
    def request(self, name: str):
        cmd, length, parse = P.READ_ONLY[name]
        return parse(self.transact(P.code(cmd), length))

    def snapshot(self) -> dict:
        out = {}
        for name in ("state", "print", "surface", "chamber", "live", "countdown"):
            try:
                out[name] = self.request(name)
            except P.ProtocolError as e:
                out[name] = e
        return out

    # commands that change something -----------------------------------------
    def command(self, payload: bytes, strict: bool = False) -> None:
        """strict: auch das Erfolgs-Byte der Antwort prüfen (wie Central bei Scaling und Testmustern)."""
        ans = self.transact(payload, P.OK_LENGTH)
        c = P.code_of(ans)
        if c != P.SIG_OPERATIONSUCCESSFUL:
            if c == P.SIG_UNKNOWN_COMMAND:
                raise P.ProtocolError("Kit kennt den Befehl nicht")
            raise P.ProtocolError(f"Kit hat nicht bestätigt (Antwort {c})")
        if strict and len(ans) >= 3 and ans[2] == 0:
            raise P.ProtocolError("Kit meldet: nicht erfolgreich")

    def close(self) -> None:
        self.t.close()
