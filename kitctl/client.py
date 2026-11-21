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


def _usb_holders(dev) -> list[str]:
    """Welche Prozesse haben das USB-Gerät offen? (/proc/*/fd -> /dev/bus/usb/BBB/DDD)"""
    import os
    target = f"/dev/bus/usb/{dev.bus:03d}/{dev.address:03d}"
    me, out = os.getpid(), []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                if os.readlink(f"/proc/{pid}/fd/{fd}") == target:
                    with open(f"/proc/{pid}/comm") as f:
                        out.append(f"{f.read().strip()} (PID {pid})")
                    break
        except OSError:
            continue
    return out


def usb_diag(dev) -> str:
    """Kurzbeschreibung der USB-Schnittstellen des Kits samt gebundenem Linux-Treiber."""
    import os
    try:
        path = f"{dev.bus}-" + ".".join(str(p) for p in (dev.port_numbers or ()))
    except Exception:
        path = "?"
    parts = []
    try:
        cfg = dev.get_active_configuration()
        parts.append(f"Konfig {cfg.bConfigurationValue}")
    except Exception as e:
        cfg = None
        parts.append(f"Konfig ? ({e})")
    try:
        for c in dev:
            for intf in c:
                eps = "/".join(f"{ep.bEndpointAddress:02x}" for ep in intf)
                drv = "-"
                link = f"/sys/bus/usb/devices/{path}:{c.bConfigurationValue}.{intf.bInterfaceNumber}/driver"
                if os.path.islink(link):
                    drv = os.path.basename(os.readlink(link))
                parts.append(f"IF{intf.bInterfaceNumber}.{intf.bAlternateSetting} Kl.{intf.bInterfaceClass:02x} EP {eps} Treiber {drv}")
    except Exception as e:
        parts.append(f"Deskriptoren nicht lesbar ({e})")
    return f"USB {path}: " + "; ".join(parts)


class UsbTransport:
    """Wie Central (usb4java/libusb, USBV_HandShake):
    Gerät 03eb:8002 öffnen, Kernel-Treiber lösen, Interface 0 beanspruchen,
    Alt-Setting 0 setzen, dann Bulk OUT 0x06 / Bulk IN 0x85 mit 2000 ms Timeout.
    Bei Fehlern wird alles wieder freigegeben (sonst bleibt das Interface belegt: „Resource busy“)."""

    def __init__(self, timeout_ms: int = P.TIMEOUT_MS):
        try:
            import usb.core
            import usb.util
        except ImportError as e:  # pragma: no cover
            raise SystemExit("pyusb fehlt: sudo apt install python3-usb") from e
        self._usb = usb
        self.timeout = timeout_ms
        self._reattach = False
        self.dev = None
        last = None
        for attempt in range(2):
            dev = usb.core.find(idVendor=P.VENDOR_ID, idProduct=P.PRODUCT_ID)
            if dev is None:
                raise SystemExit("Kein Kit gefunden (USB 03eb:8002). Kabel und Strom prüfen.")
            try:
                self._open(dev)
                self.dev = dev
                break
            except usb.core.USBError as e:
                last = e
                self._cleanup(dev)
                if getattr(e, "errno", None) == 16 and attempt == 0:
                    # Belegt: Gerät einmal zurücksetzen und neu suchen (wie ein Abziehen/Anstecken)
                    try:
                        dev.reset()
                    except usb.core.USBError:
                        pass
                    import time
                    time.sleep(1.5)
                    continue
                break
        if self.dev is None:
            if getattr(last, "errno", None) == 16:
                who = _usb_holders(dev)
                raise P.ProtocolError("USB-Schnittstelle des Kits ist belegt"
                                      + (f" von {', '.join(who)}" if who else " (anderes Programm?)"))
            raise P.ProtocolError(f"USB-Fehler bei „{getattr(self, 'step', 'Öffnen')}“: {last} · {usb_diag(dev)}")
        self.diag = usb_diag(self.dev)
        self._flush()

    def _open(self, dev) -> None:
        usb = self._usb
        self.step = "Kernel-Treiber lösen"
        try:
            if dev.is_kernel_driver_active(P.INTERFACE):
                dev.detach_kernel_driver(P.INTERFACE)
                self._reattach = True
        except NotImplementedError:
            pass
        self.step = "Interface 0 beanspruchen"
        usb.util.claim_interface(dev, P.INTERFACE)
        self.step = "Alt-Setting 0"
        try:
            dev.set_interface_altsetting(interface=P.INTERFACE, alternate_setting=0)
        except usb.core.USBError:
            pass   # manche Firmwares antworten mit STALL, obwohl es nur ein Alt-Setting gibt

    def _flush(self) -> None:
        """Alte Antworten im Puffer verwerfen (z. B. nach einem abgebrochenen Lauf)."""
        for _ in range(4):
            try:
                self.dev.read(P.EP_IN, P.BULK_BUFFER, timeout=50)
            except self._usb.core.USBError:
                return

    def _cleanup(self, dev) -> None:
        u = self._usb.util
        try:
            u.release_interface(dev, P.INTERFACE)
        except Exception:
            pass
        if self._reattach:
            try:
                dev.attach_kernel_driver(P.INTERFACE)
            except Exception:
                pass
            self._reattach = False
        try:
            u.dispose_resources(dev)
        except Exception:
            pass

    def _retry(self, what: str, ep: int, fn):
        usb = self._usb
        try:
            return fn()
        except usb.core.USBError as e:
            if getattr(e, "errno", None) not in (5, 32):   # E/A-Fehler oder Stall
                raise
            try:
                self.dev.clear_halt(ep)
            except usb.core.USBError:
                pass
            try:
                return fn()
            except usb.core.USBError as e2:
                raise P.ProtocolError(f"USB {what} (EP {ep:02x}): {e2} · {getattr(self, 'diag', '')}") from e2

    def write(self, data: bytes) -> None:
        n = self._retry("Senden", P.EP_OUT, lambda: self.dev.write(P.EP_OUT, data, timeout=self.timeout))
        if n != len(data):
            raise P.ProtocolError(f"nur {n} von {len(data)} Bytes gesendet")

    def read(self, size: int) -> bytes:
        return bytes(self._retry("Empfangen", P.EP_IN, lambda: self.dev.read(P.EP_IN, max(size, P.BULK_BUFFER), timeout=self.timeout)))

    def close(self) -> None:
        if self.dev is not None:
            self._cleanup(self.dev)
            self.dev = None


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
