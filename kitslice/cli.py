"""Slicen und senden ohne Oberfläche.

  python -m kitslice.cli slice teil.stl [weitere.stl] --profile pa12 -o job.bin
  python -m kitslice.cli send job.bin --host 192.168.1.50 [--start]
  python -m kitslice.cli profiles
  python -m kitslice.cli discover
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kitslice")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("slice")
    s.add_argument("stl", nargs="+")
    s.add_argument("--profile", default="pa12")
    s.add_argument("-o", "--out", default="job.bin")
    s.add_argument("--no-arrange", action="store_true")
    s.add_argument("--send", metavar="HOST")
    s.add_argument("--start", action="store_true")
    n = sub.add_parser("send")
    n.add_argument("job")
    n.add_argument("--host", required=True)
    n.add_argument("--start", action="store_true")
    n.add_argument("--profile")
    sub.add_parser("profiles")
    sub.add_parser("discover")
    a = ap.parse_args(argv)

    from kitslice import profiles
    if a.cmd == "profiles":
        for p in profiles.listing():
            print(f"{p['id']:16} {p['name']:24} {'Vorlage' if p['builtin'] else 'eigen'}  "
                  f"{p['layer_um']} µm, Schraffur {p['hatch_spacing_um']} µm")
        return 0
    if a.cmd == "discover":
        from kitslice.net import discover
        for d in discover():
            print(f"{d['name']}  {d['host']}:{d['port']}")
        return 0
    if a.cmd == "slice":
        from kitslice.job import make_job
        from kitslice.scene import Part, Scene
        prof = profiles.get(a.profile)
        sc = Scene()
        for f in a.stl:
            sc.add(Part.load(f))
        if not a.no_arrange and not sc.arrange():
            print("Warnung: Bauteile passen nicht nebeneinander in den Bauraum", file=sys.stderr)
        last = [-1]

        def prog(f):
            pc = int(f * 100)
            if pc != last[0]:
                last[0] = pc
                print(f"\r{pc:3d} %", end="", file=sys.stderr, flush=True)
        try:
            data, meta, _ = make_job(sc, prof, prog)
        except ValueError as e:
            print(f"\nFehler: {e}", file=sys.stderr)
            return 1
        print(file=sys.stderr)
        with open(a.out, "wb") as f:
            f.write(data)
        print(json.dumps(meta, ensure_ascii=False))
        if a.send:
            return _send(a.send, data, os.path.basename(a.stl[0]), prof, a.start)
        return 0
    if a.cmd == "send":
        with open(a.job, "rb") as f:
            data = f.read()
        prof = profiles.get(a.profile) if a.profile else None
        return _send(a.host, data, os.path.basename(a.job), prof, a.start)
    return 2


def _send(host, data, name, prof, start) -> int:
    from kitslice.net import Pi
    r = Pi(host).send_job(data, name, prof, start)
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
