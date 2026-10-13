"""Command line entry point.

    python -m automation backup -i inventory/frr-lab.yml
    python -m automation check  -i inventory/frr-lab.yml [--json report.json]

`check` exits 0 when every check passes, 1 when any check fails and 2 on
usage/inventory errors.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from automation.backup import backup_device, backup_dir
from automation.checks import check_device, summarize
from automation.collect import collect
from automation.connection import DeviceSession
from automation.inventory import Device, load_inventory
from automation.report import render_json, render_text


def _devices(args) -> list[Device]:
    only = args.device.split(",") if args.device else None
    return load_inventory(args.inventory, only)


def cmd_backup(args) -> int:
    devices = _devices(args)
    dest = backup_dir(args.out)

    def one(dev: Device):
        try:
            with DeviceSession(dev) as s:
                return dev.name, backup_device(s, dest), None
        except Exception as exc:
            return dev.name, None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, devices))
    failed = 0
    print(f"Config backup -> {dest}")
    for name, path, err in results:
        if err:
            failed += 1
            print(f"  FAIL  {name:<8} {err}")
        else:
            size = path.stat().st_size
            print(f"  OK    {name:<8} {path.as_posix()} ({size} bytes)")
    print(f"{len(results) - failed} saved, {failed} failed")
    return 1 if failed else 0


def cmd_check(args) -> int:
    devices = _devices(args)

    def one(dev: Device):
        session = DeviceSession(dev)
        try:
            state = collect(session, ["bgp", "interfaces", "pim_neighbors"])
        finally:
            session.close()
        return check_device(state, dev.expect)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        per_device = list(pool.map(one, devices))
    results = [r for rs in per_device for r in rs]
    sys.stdout.write(render_text(results, f"Fabric health check ({Path(args.inventory).name})"))
    if args.json:
        Path(args.json).write_text(render_json(results))
    _, failed = summarize(results)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m automation", description="Data center lab automation")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, helptext in (("backup", cmd_backup, "save running configs with timestamps"),
                               ("check", cmd_check, "check BGP, interface and PIM state")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("-i", "--inventory", default="inventory/frr-lab.yml")
        sp.add_argument("-d", "--device", help="comma separated subset of devices")
        sp.add_argument("-w", "--workers", type=int, default=5)
        sp.set_defaults(func=fn)
        if name == "backup":
            sp.add_argument("-o", "--out", default="backups")
        else:
            sp.add_argument("--json", help="also write a JSON report to this file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
