#!/bin/sh
# Kernel settings every router needs: IPv4 forwarding, ECMP L4 hashing and no
# strict reverse-path filtering (PIM does its own RPF checks; strict rp_filter
# drops multicast that arrives over the "other" ECMP uplink).
sysctl -qw net.ipv4.ip_forward=1
sysctl -qw net.ipv4.fib_multipath_hash_policy=1
sysctl -qw net.ipv4.conf.all.rp_filter=0
sysctl -qw net.ipv4.conf.default.rp_filter=0
for i in /proc/sys/net/ipv4/conf/*/rp_filter; do echo 0 > "$i"; done
