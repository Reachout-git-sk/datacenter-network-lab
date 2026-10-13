#!/usr/bin/env bash
# End-to-end verification of the running dc-frr lab. Every command's real output
# is written to docs/verification/ (or $OUT) so the results can be reviewed.
#
#   scripts/verify.sh            # after: scripts/clab.sh deploy -t topologies/dc-frr.clab.yml
#
# Exit code is non-zero if a ping fails or a subscriber misses the feed.
set -uo pipefail
export MSYS_NO_PATHCONV=1
LAB="${LAB:-dc-frr}"
OUT="${OUT:-$(cd "$(dirname "$0")/.." && pwd)/docs/verification}"
ROUTERS="spine1 spine2 leaf1 leaf2 leaf3"
LEAVES="leaf1 leaf2 leaf3"
FEED_RATE=20
FEED_COUNT=600            # 30 s of feed
mkdir -p "$OUT"
fail=0

dx() { local n="$1"; shift; docker exec "clab-${LAB}-${n}" "$@"; }
vty() { local n="$1"; shift; local args=(); for c in "$@"; do args+=(-c "$c"); done; dx "$n" vtysh "${args[@]}"; }
banner() { printf '\n===== %s : %s =====\n' "$1" "$2"; }
stamp() { echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) from lab ${LAB}"; }

echo "waiting for BGP sessions..."
for _ in $(seq 1 60); do
  est=0
  for r in $ROUTERS; do
    est=$((est + $(vty "$r" "show bgp summary json" | grep -o '"state":"Established"' | wc -l)))
  done
  [ "$est" -ge 12 ] && break
  sleep 2
done
echo "established BGP sessions (counted from both ends): $est/12"

# ---------------------------------------------------------------- BGP / routes
{
  stamp
  for r in $ROUTERS; do banner "$r" "show ip bgp summary"; vty "$r" "show ip bgp summary"; done
} > "$OUT/01-bgp-summary.txt"

{
  stamp
  for r in leaf1 spine1; do banner "$r" "show ip route"; vty "$r" "show ip route"; done
  banner leaf1 "show ip route 10.10.3.0/24 (ECMP over both spines)"
  vty leaf1 "show ip route 10.10.3.0/24"
  banner leaf1 "ip route show 10.10.3.0/24 (kernel FIB)"
  dx leaf1 ip route show 10.10.3.0/24
  banner leaf1 "show ip bgp 10.10.3.0/24"
  vty leaf1 "show ip bgp 10.10.3.0/24"
} > "$OUT/02-ip-route.txt"

# ---------------------------------------------------------------- VLANs / ping
{
  stamp
  for l in $LEAVES; do
    banner "$l" "bridge vlan show"; dx "$l" bridge vlan show
    banner "$l" "ip -br addr show (SVIs)"; dx "$l" ip -br addr show
  done
} > "$OUT/03-vlans-svis.txt"

ping_pair() {   # src dst label
  banner "$1 -> $2" "$3"
  if dx "$1" ping -c 3 -W 2 "$2"; then echo "RESULT: PASS"; else echo "RESULT: FAIL"; fail=1; fi
}
{
  stamp
  ping_pair h11 10.20.1.10 "inter-VLAN on leaf1 (VLAN10 -> VLAN20)"
  ping_pair h11 10.10.2.10 "leaf1 VLAN10 -> leaf2 VLAN10 (across the fabric)"
  ping_pair h11 10.20.3.10 "leaf1 VLAN10 -> leaf3 VLAN20 (across the fabric, inter-VLAN)"
  ping_pair h22 10.10.3.10 "leaf2 VLAN20 -> leaf3 VLAN10 (across the fabric, inter-VLAN)"
  banner h11 "traceroute 10.20.3.10"
  dx h11 traceroute -n -w 1 -q 1 10.20.3.10
} > "$OUT/04-ping-inter-vlan.txt" 2>&1
grep -q "RESULT: FAIL" "$OUT/04-ping-inter-vlan.txt" && fail=1

# ---------------------------------------------------------------- multicast
# subscribers: h21 (leaf2 VLAN10), h32 (leaf3 VLAN20), h12 (leaf1 VLAN20)
# control:     h22 (leaf2 VLAN20) does not join; tcpdump counts what reaches it
SUBS="h21:10.10.2.10 h32:10.20.3.10 h12:10.20.1.10"
DUR=$(( FEED_COUNT / FEED_RATE + 15 ))
for s in $SUBS; do
  n=${s%%:*}; ip=${s##*:}
  dx "$n" rm -f /tmp/sub.json
  dx "$n" sh -c "nohup python3 /opt/mcast/subscriber.py --iface-addr $ip --duration $DUR > /tmp/sub.json 2>&1 &"
done
dx h22 sh -c "rm -f /tmp/ctl.txt; nohup timeout $DUR tcpdump -nli eth1 udp port 5001 > /tmp/ctl.txt 2>/dev/null &"
sleep 5   # let IGMP reports reach the leaves
dx h11 sh -c "nohup python3 /opt/mcast/publisher.py --rate $FEED_RATE --count $FEED_COUNT > /tmp/pub.json 2>&1 &"
sleep 12  # feed is flowing: capture control-plane state now

{
  stamp
  for r in $ROUTERS; do banner "$r" "show ip pim neighbor"; vty "$r" "show ip pim neighbor"; done
  for r in $ROUTERS; do banner "$r" "show ip pim rp-info"; vty "$r" "show ip pim rp-info"; done
} > "$OUT/05-pim-neighbor-rp.txt"
{
  stamp
  for l in $LEAVES; do
    banner "$l" "show ip igmp groups"; vty "$l" "show ip igmp groups"
    banner "$l" "show ip igmp interface"; vty "$l" "show ip igmp interface"
    banner "$l" "bridge mdb show (IGMP snooping table)"; dx "$l" bridge mdb show
  done
} > "$OUT/06-igmp-groups.txt"
{
  stamp
  for r in $ROUTERS; do
    banner "$r" "show ip mroute"; vty "$r" "show ip mroute"
    banner "$r" "show ip pim join"; vty "$r" "show ip pim join"
  done
  for r in $ROUTERS; do banner "$r" "ip mroute show (kernel multicast forwarding cache)"; dx "$r" ip mroute show; done
  for r in spine1 leaf1 leaf2 leaf3; do banner "$r" "show ip mroute count"; vty "$r" "show ip mroute count"; done
} > "$OUT/07-mroute.txt"

echo "waiting for the feed to finish..."
for _ in $(seq 1 $((DUR + 10))); do
  done_count=0
  for s in $SUBS; do dx "${s%%:*}" grep -q received /tmp/sub.json 2>/dev/null && done_count=$((done_count + 1)); done
  [ "$done_count" -eq 3 ] && break
  sleep 2
done
{
  stamp
  echo "feed: h11 (10.10.1.10, leaf1 VLAN10) -> 239.1.1.1:5001, ${FEED_RATE} pkt/s, ${FEED_COUNT} packets"
  banner h11 "publisher"; dx h11 cat /tmp/pub.json
  for s in $SUBS; do banner "${s%%:*}" "subscriber"; dx "${s%%:*}" cat /tmp/sub.json; done
  banner h22 "control host (no IGMP join), packets seen on the wire"
  dx h22 sh -c 'grep -c "239.1.1.1" /tmp/ctl.txt || true'
} > "$OUT/08-multicast-receive.txt"

for s in $SUBS; do
  got=$(dx "${s%%:*}" sh -c "grep -o '\"received\": [0-9]*' /tmp/sub.json | grep -o '[0-9]*$'")
  echo "${s%%:*} received ${got:-0}/${FEED_COUNT}"
  # allow the very first packet to be lost while the shared tree is being built
  [ "${got:-0}" -ge $((FEED_COUNT - 5)) ] || fail=1
done
ctl=$(dx h22 sh -c 'grep -c "239.1.1.1" /tmp/ctl.txt || true')
echo "h22 (not subscribed) saw ${ctl} feed packets"

if [ "$fail" -eq 0 ]; then echo "VERIFY: PASS"; else echo "VERIFY: FAIL"; fi
exit "$fail"
