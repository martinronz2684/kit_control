"""Simulierter Kit für KIT_DEMO=1 (Oberfläche ohne Hardware testen)."""
import struct
import time

from kitctl import protocol as P


class DemoTransport:
    def __init__(self):
        self.t0 = time.time()
        self.chamber_target = 145.0
        self.targets = [150.0, 140.0, 170.0, 140.0]   # sw, cw, sp, cp
        self.laser = 650.0
        self.printing = False      # startet bereit; „Druck starten“ unter Jobs startet einen simulierten Druck
        self.layers = 680
        self.powder = False
        self.scaling = [1.0, 1.0, 1.0]
        self._next = b""

    def write(self, data):
        c = P.code_of(data)
        le = lambda v: struct.pack("<i", int(v))
        t = time.time() - self.t0
        if c == P.COM_IDENTIFY:
            self._next = P.code(P.SIG_IDENTIFY) + struct.pack("<III", 4, 4, 12) + bytes(16)
        elif c == P.COM_REQUESTGENERALPRINTERSTATE:
            st = 7 if self.printing else (4 if self.powder else 1)
            self._next = P.code(P.SIG_GENERALPRINTERSTATE) + bytes([st]) + le(0) + le(0)
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
            self._next = P.code(P.SIG_LIVEPARAMETERS1) + b"".join(le(v * 1000) for v in (self.targets[1], self.targets[0], self.targets[3], self.targets[2], self.laser))
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
        elif c in (P.COM_GO_POWDERPREPARATION, P.COM_EXIT_POWDERPREPARATION):
            self.powder = c == P.COM_GO_POWDERPREPARATION
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_REQUEST_SCALINGPARAMETERS1:
            self._next = P.code(P.SIG_SCALINGPARAMETERS1) + b"".join(le(v * 10000) for v in self.scaling)
        elif c == P.COM_SET_SCALINGPARAMETERS1:
            self.scaling = [struct.unpack_from("<i", data, 2 + 4 * k)[0] / 10000 for k in range(3)]
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_SET_TARGETTEMPERATURES1:
            self.targets = [struct.unpack_from("<i", data, 2 + 4 * k)[0] / 1000 for k in range(4)]
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_GENERALLASERSPEED:
            self.laser = struct.unpack_from("<i", data, 2)[0] / 1000
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        elif c == P.COM_TARGET_CHAMBER_PRINT:
            self.chamber_target = struct.unpack_from("<i", data, 2)[0] / 1000
            self.targets[3] = self.chamber_target
            self._next = P.code(P.SIG_OPERATIONSUCCESSFUL) + b"\x01"
        else:
            self._next = P.code(P.SIG_OPERATION_SUCCESSFUL if c == P.COM_CONNECTION_ESTABLISHED else P.SIG_OPERATIONSUCCESSFUL) + b"\x01"

    def read(self, size):
        return self._next

    def close(self):
        pass
