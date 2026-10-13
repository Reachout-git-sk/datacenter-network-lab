#!/usr/bin/env python3
"""Market-data style multicast feed publisher.

Sends one UDP datagram per tick to a multicast group. Each datagram is a small
JSON quote with a monotonically increasing sequence number so subscribers can
count what they received and detect gaps.

    python3 publisher.py --group 239.1.1.1 --port 5001 --rate 20 --count 600
"""
import argparse
import json
import random
import socket
import time

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA", "JPM"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--group", default="239.1.1.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--rate", type=float, default=20.0, help="packets per second")
    ap.add_argument("--count", type=int, default=0, help="0 = run forever")
    ap.add_argument("--ttl", type=int, default=16)
    ap.add_argument("--source", default="", help="local address to send from")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, args.ttl)
    if args.source:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(args.source))

    prices = {s: random.uniform(50, 900) for s in SYMBOLS}
    interval = 1.0 / args.rate
    seq = 0
    start = time.time()
    print(f"publishing to {args.group}:{args.port} at {args.rate}/s ttl={args.ttl}", flush=True)
    try:
        while args.count == 0 or seq < args.count:
            seq += 1
            sym = random.choice(SYMBOLS)
            prices[sym] *= 1 + random.gauss(0, 0.0005)
            msg = {"seq": seq, "ts": time.time(), "sym": sym, "px": round(prices[sym], 4),
                   "qty": random.randint(1, 50) * 100}
            sock.sendto(json.dumps(msg).encode(), (args.group, args.port))
            # keep a steady rate regardless of how long the send took
            time.sleep(max(0.0, start + seq * interval - time.time()))
    except KeyboardInterrupt:
        pass
    print(json.dumps({"role": "publisher", "group": args.group, "sent": seq,
                      "seconds": round(time.time() - start, 2)}), flush=True)


if __name__ == "__main__":
    main()
