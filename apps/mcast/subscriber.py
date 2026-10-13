#!/usr/bin/env python3
"""Multicast feed subscriber.

Joins the group (this triggers an IGMP membership report towards the leaf),
counts datagrams for --duration seconds and prints a one-line JSON summary:
packets received, first/last sequence number and the number of gaps.

    python3 subscriber.py --group 239.1.1.1 --port 5001 --iface-addr 10.10.2.10 --duration 40
"""
import argparse
import json
import socket
import struct
import time


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--group", default="239.1.1.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--iface-addr", required=True, help="address of the host-facing interface")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--name", default=socket.gethostname())
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", args.port))
    mreq = struct.pack("4s4s", socket.inet_aton(args.group), socket.inet_aton(args.iface_addr))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(0.5)

    received, first, last, gaps, senders = 0, None, None, 0, set()
    deadline = time.time() + args.duration
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        try:
            seq = json.loads(data)["seq"]
        except (ValueError, KeyError):
            continue
        received += 1
        senders.add(addr[0])
        if first is None:
            first = seq
        elif last is not None and seq != last + 1:
            gaps += 1
        last = seq

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
    print(json.dumps({"role": "subscriber", "host": args.name, "group": args.group,
                      "received": received, "first_seq": first, "last_seq": last,
                      "gaps": gaps, "senders": sorted(senders)}), flush=True)


if __name__ == "__main__":
    main()
