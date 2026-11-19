"""Simulierter Kit für KIT_DEMO=1 (Oberfläche ohne Hardware testen)."""
import struct
import time

from kitctl import protocol as P


class DemoTransport:
    def __init__(self):
        self.t0 = time.time()
        self.chamber_target = 145.0
        self.printing = False      # startet bereit; „Druck starten“ unter Jobs startet einen simulierten Druck
        self.layers = 680
        self._next = b""

    def write(self, data):
        c = P.code_of(data)
        le = lambda v: struct.pack("<i", int(v))
        t = time.time() - self.t0
        if c == P.COM_IDENTIFY:
            self._next = P.code(P.SIG_IDENTIFY) + struct.pack("<III", 4, 4, 12) + bytes(16)
        elif c == P.COM_REQUESTGENERALPRINTERSTATE:
            self._next = P.code(P.SIG_GENERALPRINTERSTATE) + b"\x03" + le(0) + le(0)
        elif c == P.COM_REQUESTPRINTSTATUS:
            layer = min(self.layers, int(t / 2)) if self.printing else 0
            if self.printing and layer >= self.layers:
                self.printing = False
            self._next = P.code(P.SIG_PRINTSTATUS) + bytes([1 if self.printing else 0]) + le(layer) + le(t if self.printing else 0) + le(layer * 100 // self.layers)
        elif c == P.COM_REQUESTPOWDERSURFACETEMP:
            self._next = P.code(P.SIG_SINGLETEMPERATURE) + le(168400 + 600 * ((t % 7) - 3.5))
        elif c == P.COM_REQUESTCHAMBERTEMP:
            self._next = P.code(P.SIG_SINGLETEMPERATURE) + le(141200 + 300 * ((t % 11) - 5.5))
        elif c == P.COM_REQUEST_LIVEPARAMETERS1:
            self._next = P.code(P.SIG_LIVEPARAMETERS1) + b"".join(le(v) for v in (130000, 150000, self.chamber_target * 1000, 170000, 1500000))
        elif c == P.COM_REQUEST_PRINTWARMUPCOUNTDOWN:
            self._next = P.code(P.SIG_WARMUPPRINTCOUNTDOWN) + b"\x00" + le(0)
        elif c == P.COM_REQUEST_WARNINGFRAME:
            self._next = P.code(P.SIG_WARNINGFRAME) + b"\x01" + le(95)
        elif c == P.COM_REQUEST_ERRORFRAME:
            self._next = P.code(P.SIG_ERRORFRAME) + b"\x00"
        elif c == P.COM_STARTPRINT:
            self.printing = True
            self.t0 = time.time()
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_ABORTPRINT:
            self.printing = False
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_TARGET_CHAMBER_PRINT:
            self.chamber_target = struct.unpack_from("<i", data, 2)[0] / 1000
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        else:
            self._next = P.code(P.SIG_OPERATION_SUCCESSFUL if c == P.COM_CONNECTION_ESTABLISHED else P.SIG_OPERATIONSUCCESSFUL) + b"\x01"

    def read(self, size):
        return self._next

    def close(self):
        pass
