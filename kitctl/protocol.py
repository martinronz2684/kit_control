"""Sintratec Kit USB protocol (read from Sintratec Central 1.2.0 bytecode).

Everything here was taken from the decompiled classes in
sintratec-comm-nio-1.2.0.jar and sintratec-central-kit-1.2.0.jar:

* packets start with a 2-byte little-endian code
* 4-byte values are little-endian int32; temperatures and speeds are value / 1000
* every command gets exactly one fixed-length answer on the IN endpoint

This module only builds and parses bytes. It does no USB I/O.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# --- USB ------------------------------------------------------------------
VENDOR_ID = 0x03EB          # Atmel   (Central: VID 1003)
PRODUCT_ID = 0x8002         #         (Central: PID -32766 as Java short)
INTERFACE = 0               # Central claims interface 0 (the SD card is a separate MSC interface)
EP_OUT = 0x06               # PrinterSpecUSBV.getCommandBulkOutEndPoint()
EP_IN = 0x85                # PrinterSpecUSBV.getSignalBulkInEndPoint()
BULK_BUFFER = 512           # PrinterSpecKit.getBulkBufferSize()
TIMEOUT_MS = 2000           # Central uses 2000 ms for every bulk transfer

# --- Handshake codes (USBV_HandShake$HandShakePacketCode) -----------------
SIG_COMMAND_NOT_RECOGNISED = 5000
COM_CONNECTION_ESTABLISHED = 5001
SIG_IDENTIFY = 5002
COM_IDENTIFY = 5003
COM_LOAD_BOOTLOADER = 5004          # never sent by this tool
SIG_OPERATION_SUCCESSFUL = 5005
COM_FIRMWARE_FLASHING_REQUEST = 5006  # never sent by this tool

# --- Kit codes (ch.sintratec.central.printers.kit.KitPacketCode) ----------
COM_GO = 1
COM_JUMP = 2
COM_REQUESTPRINTERID = 5
COM_TESTPATTERN = 6
COM_REQUESTPROGRESS = 7
COM_REQUESTTEMPERATURES = 8
COM_STARTPRINT = 14
COM_ABORTPRINT = 15
COM_REQUESTPOWDERSURFACETEMP = 16
COM_REQUESTCHAMBERTEMP = 17
COM_REQUESTGENERALPRINTERSTATE = 19
COM_REQUESTPRINTSTATUS = 21
COM_GENERALLASERSPEED = 23
COM_MOVEPOWDERRESERVOIRPLATFORM = 24
COM_MOVEPOWDERPRINTPLATFORM = 25
COM_REQUESTSINGLEIRTEMP = 26
COM_MAKELAYER = 27
COM_INITSYSTEM = 30
COM_WARMUPMODE = 35
COM_TARGET_POWDERSURFACE_WARMUP = 44
COM_TARGET_POWDERSURFACE_PRINT = 46
COM_TARGET_CHAMBER_WARMUP = 47
COM_TARGET_CHAMBER_PRINT = 49
COM_CONNECTIONESTABLISHED = 52
COM_FORCESTART_SINTERING = 53
COM_FORCESTART_SURFACE_WARMUP = 54
COM_STOPSINTERING_GOCOOLDOWN = 55
COM_EXITCALIBRATION = 56
COM_REQUEST_LIVEPARAMETERS1 = 57
COM_REQUEST_SCALINGPARAMETERS1 = 60
COM_SET_SCALINGPARAMETERS1 = 61
COM_SET_TARGETTEMPERATURES1 = 62
COM_REQUEST_PRINTWARMUPCOUNTDOWN = 64
COM_GO_POWDERPREPARATION = 65
COM_EXIT_POWDERPREPARATION = 66
COM_REQUEST_ERRORFRAME = 67
COM_REQUEST_WARNINGFRAME = 68
COM_SETLASERSPEED_CONTOUR = 71
COM_GOS_INFILL_FOLLOW = 72
COM_GOS_CONTOUR_FOLLOW = 73
COM_FREEZE_ALL_MOTOR_FUNCTIONS = 74
COM_SET_RIGHT_LAMP_POWER = 32   # SetRightLampPowerKit.PACKET_CODE
COM_SET_FRONT_LAMP_POWER = 33   # SetFrontLampPowerKit.PACKET_CODE
COM_SET_LEFT_LAMP_POWER = 34    # SetLeftLampPowerKit.PACKET_CODE

SIG_OPERATIONSUCCESSFUL = 8
SIG_UNKNOWN_COMMAND = 12
SIG_PROGRESS = 18
SIG_SINGLETEMPERATURE = 18
SIG_GENERALPRINTERSTATE = 20
SIG_PRINTSTATUS = 22
SIG_LIVEPARAMETERS1 = 58
SIG_SCALINGPARAMETERS1 = 59
SIG_WARMUPPRINTCOUNTDOWN = 63
SIG_ERRORFRAME = 69
SIG_WARNINGFRAME = 70

# Kit models known to Central 1.2.0
KIT_MODELS = {
    2: ("KitCrowdfundedUSBV", "stec_kit2_firm12_t107.bin"),
    4: ("KitM2USBV", "stec_kit4_firm12_t107.bin"),
}
SUPPORTED_FIRMWARE = 12
SUPPORTED_PROTOCOL = 4

STATE_WAITING_FOR_SD_CARD = 200  # GeneralPrinterStateKit


class ProtocolError(Exception):
    pass


def code(n: int) -> bytes:
    return struct.pack("<H", n)


def code_of(buf: bytes) -> int:
    if len(buf) < 2:
        raise ProtocolError(f"answer too short ({len(buf)} bytes)")
    return struct.unpack_from("<H", buf)[0]


def i32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<i", buf, off)[0]


def u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def mm_to_um(mm: float) -> bytes:
    """CommandBin.doubleMMToInt32LittleEndianUM"""
    return struct.pack("<i", round(mm * 1000))


def expect(buf: bytes, sig: int, length: int) -> None:
    c = code_of(buf)
    if c != sig:
        if c in (SIG_COMMAND_NOT_RECOGNISED, SIG_UNKNOWN_COMMAND):
            raise ProtocolError(f"printer did not recognise the command (answer code {c})")
        raise ProtocolError(f"expected answer code {sig}, got {c}")
    if len(buf) < length:
        raise ProtocolError(f"answer {sig}: expected {length} bytes, got {len(buf)}")


# --- Answers ----------------------------------------------------------------
@dataclass
class Identity:
    model: int
    comm: int
    firmware: int
    uid: bytes

    LENGTH = 30  # code(2) model(4) comm(4) firm(4) id(16)

    @classmethod
    def parse(cls, buf: bytes) -> "Identity":
        expect(buf, SIG_IDENTIFY, cls.LENGTH)
        return cls(u32(buf, 2), u32(buf, 6), u32(buf, 10), bytes(buf[14:30]))

    @property
    def model_name(self) -> str:
        if self.model == 0:
            return "Recovery-Bootloader"
        return KIT_MODELS.get(self.model, (f"unbekannt ({self.model})",))[0]

    @property
    def is_supported_kit(self) -> bool:
        return (self.model in KIT_MODELS and self.firmware == SUPPORTED_FIRMWARE
                and self.comm == SUPPORTED_PROTOCOL)


@dataclass
class GeneralState:
    state: int
    warnings: int
    errors: int
    LENGTH = 11  # code(2) state(1) warnings(4) errors(4)

    @classmethod
    def parse(cls, buf: bytes) -> "GeneralState":
        expect(buf, SIG_GENERALPRINTERSTATE, cls.LENGTH)
        return cls(buf[2], i32(buf, 3), i32(buf, 7))


@dataclass
class PrintStatus:
    printing: bool
    layer: int
    elapsed_s: int
    percent: int
    LENGTH = 15  # code(2) printing(1) layer(4) elapsed(4) percent(4)

    @classmethod
    def parse(cls, buf: bytes) -> "PrintStatus":
        expect(buf, SIG_PRINTSTATUS, cls.LENGTH)
        return cls(buf[2] == 1, i32(buf, 3), i32(buf, 7), i32(buf, 11))


@dataclass
class Temperature:
    celsius: float
    LENGTH = 6  # code(2) value(4) / 1000

    @classmethod
    def parse(cls, buf: bytes) -> "Temperature":
        expect(buf, SIG_SINGLETEMPERATURE, cls.LENGTH)
        return cls(i32(buf, 2) / 1000.0)


@dataclass
class LiveParameters:
    chamber_warmup: float
    surface_warmup: float
    chamber_print: float
    surface_print: float
    laser_speed: float
    LENGTH = 22  # code(2) + 5 x int32 / 1000

    @classmethod
    def parse(cls, buf: bytes) -> "LiveParameters":
        expect(buf, SIG_LIVEPARAMETERS1, cls.LENGTH)
        return cls(*(i32(buf, 2 + 4 * k) / 1000.0 for k in range(5)))


@dataclass
class WarmupCountdown:
    enabled: bool
    seconds: int
    LENGTH = 7  # code(2) enabled(1) secs(4)

    @classmethod
    def parse(cls, buf: bytes) -> "WarmupCountdown":
        expect(buf, SIG_WARMUPPRINTCOUNTDOWN, cls.LENGTH)
        return cls(buf[2] == 1, i32(buf, 3))


@dataclass
class Frame:
    """Error/warning frame (ErrorFrame/WarningFrame): code(2) count(1) then count x int32 codes."""
    codes: list
    LENGTH = 512

    @classmethod
    def parse(cls, buf: bytes, sig: int) -> "Frame":
        expect(buf, sig, 3)
        n = buf[2]
        if len(buf) < 3 + 4 * n:
            raise ProtocolError(f"Liste mit {n} Einträgen, aber nur {len(buf)} Bytes")
        return cls([i32(buf, 3 + 4 * k) for k in range(n)])

    @property
    def nonzero(self) -> bool:
        return bool(self.codes)


# --- Read-only requests: (command code, answer length, parser) ----------------
READ_ONLY = {
    "state": (COM_REQUESTGENERALPRINTERSTATE, GeneralState.LENGTH, GeneralState.parse),
    "print": (COM_REQUESTPRINTSTATUS, PrintStatus.LENGTH, PrintStatus.parse),
    "surface": (COM_REQUESTPOWDERSURFACETEMP, Temperature.LENGTH, Temperature.parse),
    "chamber": (COM_REQUESTCHAMBERTEMP, Temperature.LENGTH, Temperature.parse),
    "live": (COM_REQUEST_LIVEPARAMETERS1, LiveParameters.LENGTH, LiveParameters.parse),
    "countdown": (COM_REQUEST_PRINTWARMUPCOUNTDOWN, WarmupCountdown.LENGTH, WarmupCountdown.parse),
    "errors": (COM_REQUEST_ERRORFRAME, Frame.LENGTH, lambda b: Frame.parse(b, SIG_ERRORFRAME)),
    "warnings": (COM_REQUEST_WARNINGFRAME, Frame.LENGTH, lambda b: Frame.parse(b, SIG_WARNINGFRAME)),
}

# Codes this tool refuses to send, whatever the caller asks for.
FORBIDDEN = {COM_LOAD_BOOTLOADER, COM_FIRMWARE_FLASHING_REQUEST}


# --- Commands that change something (all answer with OperationSuccessful, 3 bytes) ---
OK_LENGTH = 3  # OperationSuccessfulKit.LENGTH


def i32le(v: float) -> bytes:
    return struct.pack("<i", int(round(v)))


def cmd_move(platform: str, mm: float, relative: bool = True) -> bytes:
    """MovePrintPlatformKit / MoveReservoirPlatformKit: code, type (0=RELATIVE, 1=ABSOLUT), distance in um.

    The sign convention (which direction is positive) is not visible in Central's code;
    test with 0.1 mm first.
    """
    c = {"print": COM_MOVEPOWDERPRINTPLATFORM, "reservoir": COM_MOVEPOWDERRESERVOIRPLATFORM}[platform]
    return code(c) + bytes([0 if relative else 1]) + mm_to_um(mm)


def cmd_make_layer(thickness_mm: float) -> bytes:
    """ApplyPowderLayerKit: COM_MAKELAYER + layer height in um."""
    return code(COM_MAKELAYER) + mm_to_um(thickness_mm)


def cmd_lamp(which: str, percent: float) -> bytes:
    """Set{Left,Right,Front}LampPowerKit: code + int32(percent * 10)."""
    c = {"left": COM_SET_LEFT_LAMP_POWER, "right": COM_SET_RIGHT_LAMP_POWER, "front": COM_SET_FRONT_LAMP_POWER}[which]
    return code(c) + i32le(max(0.0, min(100.0, percent)) * 10)


def cmd_target(which: str, celsius: float) -> bytes:
    """TargetChamberWarmup etc.: code + int32(celsius * 1000)."""
    c = {"chamber_warmup": COM_TARGET_CHAMBER_WARMUP, "chamber_print": COM_TARGET_CHAMBER_PRINT,
         "surface_warmup": COM_TARGET_POWDERSURFACE_WARMUP, "surface_print": COM_TARGET_POWDERSURFACE_PRINT}[which]
    return code(c) + i32le(celsius * 1000)


def cmd_targets(surface_warmup: float, chamber_warmup: float, surface_print: float, chamber_print: float) -> bytes:
    """SetTargetTemperatures1Kit: order sw, cw, sp, cp, each * 1000."""
    return code(COM_SET_TARGETTEMPERATURES1) + b"".join(
        i32le(v * 1000) for v in (surface_warmup, chamber_warmup, surface_print, chamber_print))


def cmd_warmup(on: bool) -> bytes:
    """WarmUpModeKit: code + 1 byte."""
    return code(COM_WARMUPMODE) + bytes([1 if on else 0])


def cmd_simple(c: int) -> bytes:
    return code(c)


SIMPLE = {
    "start_print": COM_STARTPRINT,
    "abort_print": COM_ABORTPRINT,
    "stop_sintering": COM_STOPSINTERING_GOCOOLDOWN,
    "freeze_motors": COM_FREEZE_ALL_MOTOR_FUNCTIONS,
    "powder_prep_on": COM_GO_POWDERPREPARATION,
    "powder_prep_off": COM_EXIT_POWDERPREPARATION,
}
