#!/usr/bin/env bash
# Background traffic for the dashboards: a continuous 200 pkt/s multicast feed
# from h11 to three subscribers, plus two unicast ping streams across the fabric.
#
#   scripts/demo-traffic.sh start | stop
set -euo pipefail
export MSYS_NO_PATHCONV=1
LAB="${LAB:-dc-frr}"
dx() { local n="$1"; shift; docker exec "clab-${LAB}-${n}" "$@"; }

case "${1:-}" in
  start)
    for s in h21:10.10.2.10 h32:10.20.3.10 h12:10.20.1.10; do
      dx "${s%%:*}" sh -c "nohup python3 /opt/mcast/subscriber.py --iface-addr ${s##*:} --duration 86400 > /tmp/demo-sub.json 2>&1 &"
    done
    sleep 3
    dx h11 sh -c "nohup python3 /opt/mcast/publisher.py --rate 200 --count 0 > /tmp/demo-pub.log 2>&1 &"
    dx h22 sh -c "nohup ping -q -i 0.05 -s 1200 10.10.3.10 > /dev/null 2>&1 &"
    dx h31 sh -c "nohup ping -q -i 0.05 -s 800 10.20.1.10 > /dev/null 2>&1 &"
    echo "demo traffic started"
    ;;
  stop)
    for h in h11 h12 h21 h22 h31 h32; do dx "$h" sh -c "pkill -f 'publisher.py|subscriber.py|ping -q' || true"; done
    echo "demo traffic stopped"
    ;;
  *) echo "usage: $0 start|stop" >&2; exit 2 ;;
esac
