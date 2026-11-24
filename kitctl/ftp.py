"""Dateiübertragung zum Kit – nachgebaut aus Central (USBV_Controller$FileOutSubmittal, USBV_FTPJ16Out).

  Host  -> [3000]                                  Anfrage Dateiübertragung
  Kit   -> [3001][bereit=1][Protokoll]             Protokoll 1 = FTPJ16
  Host  -> [3100][Dateityp][Größe int32 LE]        INIT (Druckjob = 1, Kalibrierdatei = 2)
  dann wiederholt:
  Kit   -> [3103][arg]   1 nächster Rahmen (bis 512 Byte roh)   2 Kit bricht ab
                         3 Abbruchfrage -> [3105][1=abbrechen]  4 Kit beschäftigt -> 400 ms, dann [3104]
                         5 fertig
Alle Pakete auf denselben Bulk-Endpunkten wie die Befehle (0x06 / 0x85).
"""
from __future__ import annotations

import struct
import time

REQUEST, ANSWER = 3000, 3001
INIT, MAIN_RESPONSE, FRAME_ACK, HOST_ABORT = 3100, 3103, 3104, 3105
PROTOCOL_FTPJ16 = 1
FRAME = 512
PRINT_FILE, CALIBRATION_FILE = 1, 2


class TransferError(RuntimeError):
    pass


class NotReady(TransferError):
    pass


def _c(v: int) -> bytes:
    return struct.pack("<H", v)


def _code(b: bytes) -> int:
    return b[0] | b[1] << 8 if len(b) >= 2 else -1


def send_file(t, data: bytes, ftype: int = PRINT_FILE, cancel=None, progress=None) -> None:
    """t: Transport mit write()/read(). cancel(): True = abbrechen. progress(gesendet, gesamt)."""
    t.write(_c(REQUEST))
    a = t.read(FRAME)
    if _code(a) != ANSWER or len(a) < 4:
        raise TransferError(f"falsche Antwort auf Übertragungsanfrage ({_code(a)})")
    if a[2] != 1:
        raise NotReady("Kit ist nicht bereit für eine Dateiübertragung")
    if a[3] != PROTOCOL_FTPJ16:
        raise TransferError(f"Kit verlangt unbekanntes Übertragungsprotokoll {a[3]}")
    t.write(_c(INIT) + bytes([ftype]) + struct.pack("<i", len(data)))
    sent = 0
    stalls = 0
    while True:
        r = t.read(FRAME)
        if _code(r) != MAIN_RESPONSE or len(r) < 3:
            raise TransferError(f"unerwartete Antwort während der Übertragung ({_code(r)})")
        arg = r[2]
        if arg == 1:
            chunk = data[sent:sent + FRAME]
            if not chunk:
                raise TransferError("Kit verlangt mehr Daten als die Datei hat")
            t.write(chunk)
            sent += len(chunk)
            stalls = 0
            if progress:
                progress(sent, len(data))
        elif arg == 2:
            raise TransferError("Kit hat die Übertragung abgebrochen")
        elif arg == 3:
            stop = bool(cancel and cancel())
            t.write(_c(HOST_ABORT) + bytes([1 if stop else 0]))
            if stop:
                raise TransferError("Übertragung abgebrochen")
        elif arg == 4:
            stalls += 1
            if stalls > 300:     # 2 Minuten ohne Fortschritt
                raise TransferError("Kit antwortet nicht mehr (beschäftigt)")
            time.sleep(0.4)
            t.write(_c(FRAME_ACK))
        elif arg == 5:
            if sent < len(data):
                raise TransferError("Kit meldet fertig, obwohl noch Daten fehlen")
            return
        else:
            raise TransferError(f"unbekannte Rückmeldung {arg}")
