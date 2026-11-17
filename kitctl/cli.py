"""kitctl – Kit lesend abfragen.

    kitctl identify          Modell, Protokoll, Firmware, ID
    kitctl status            einmal alle Werte
    kitctl status --watch    alle 2 s neu, Strg+C beendet
    kitctl frames            Fehler- und Warnliste (roh)
"""
from __future__ import annotations

import argparse
import sys
import time

from . import protocol as P
from .client import Kit, UsbTransport


def fmt_time(s: int) -> str:
    h, rest = divmod(max(0, s), 3600)
    return f"{h}:{rest // 60:02d} h"


def show(snap: dict) -> None:
    def line(label, value):
        print(f"  {label:<22}{value}")

    st = snap["state"]
    if isinstance(st, Exception):
        line("Zustand", f"Fehler: {st}")
    else:
        extra = " (wartet auf SD-Karte)" if st.state == P.STATE_WAITING_FOR_SD_CARD else ""
        line("Zustand", f"{st.state}{extra} · Warnungen {st.warnings} · Fehler {st.errors}")
    pr = snap["print"]
    if isinstance(pr, Exception):
        line("Druck", f"Fehler: {pr}")
    elif pr.printing:
        line("Druck", f"läuft · Schicht {pr.layer} · {pr.percent} % · {fmt_time(pr.elapsed_s)}")
    else:
        line("Druck", "kein Druck aktiv")
    for key, label in (("surface", "Pulveroberfläche"), ("chamber", "Kammer")):
        v = snap[key]
        line(label, f"Fehler: {v}" if isinstance(v, Exception) else f"{v.celsius:.1f} °C")
    lv = snap["live"]
    if not isinstance(lv, Exception):
        line("Soll Aufwärmen", f"Kammer {lv.chamber_warmup:.1f} °C · Oberfläche {lv.surface_warmup:.1f} °C")
        line("Soll Druck", f"Kammer {lv.chamber_print:.1f} °C · Oberfläche {lv.surface_print:.1f} °C")
        line("Laser-Tempo", f"{lv.laser_speed:.1f}")
    cd = snap["countdown"]
    if not isinstance(cd, Exception) and cd.enabled:
        line("Aufwärm-Countdown", f"{cd.seconds} s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kitctl", description="Sintratec Kit lesend abfragen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("identify")
    s = sub.add_parser("status")
    s.add_argument("--watch", action="store_true")
    s.add_argument("--interval", type=float, default=2.0)
    sub.add_parser("frames")
    a = ap.parse_args(argv)

    kit = Kit(UsbTransport())
    try:
        if a.cmd == "identify":
            i = kit.identify()
            print(f"Modell {i.model} ({i.model_name}) · Protokoll {i.comm} · Firmware {i.firmware}")
            print(f"ID 0x{i.uid.hex()}")
            print("unterstützt" if i.is_supported_kit else "WARNUNG: nicht die erwartete Kombination")
            return 0
        ident = kit.connect()
        print(f"Verbunden: {ident.model_name}, Firmware {ident.firmware}")
        if a.cmd == "frames":
            for name in ("errors", "warnings"):
                f = kit.request(name)
                from .codes import describe
                print(f"{'Fehler' if name == 'errors' else 'Warnungen'}: {len(f.codes) or 'keine'}")
                for c in f.codes:
                    d = describe(c)
                    print(f"  {c:>4}  {d['title']} – {d['text']}")
            return 0
        while True:
            show(kit.snapshot())
            if not a.watch:
                return 0
            time.sleep(a.interval)
            print()
    except KeyboardInterrupt:
        return 0
    except P.ProtocolError as e:
        print(f"Protokollfehler: {e}", file=sys.stderr)
        return 2
    finally:
        kit.close()


if __name__ == "__main__":
    sys.exit(main())
