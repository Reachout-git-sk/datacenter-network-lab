#!/bin/sh
# leaf2 layer-2 setup: one VLAN-aware bridge (br0) with access ports for the
# hosts and two VLAN subinterfaces of the bridge (vlan10 / vlan20) that act as
# the SVIs. Layer-3 addressing, PIM and IGMP for the SVIs live in frr.conf.
#
#   eth1 -> spine1 (routed)     eth3 -> access VLAN 10
#   eth2 -> spine2 (routed)     eth4 -> access VLAN 20
set -e
/etc/frr/sysctl.sh

ip link add br0 type bridge vlan_filtering 1 vlan_default_pvid 0     mcast_snooping 1 mcast_router 2 mcast_igmp_version 3
ip link set br0 up

bridge vlan add dev br0 vid 10 self
bridge vlan add dev br0 vid 20 self

ip link set eth3 master br0
bridge vlan add dev eth3 vid 10 pvid untagged
ip link set eth3 up

ip link set eth4 master br0
bridge vlan add dev eth4 vid 20 pvid untagged
ip link set eth4 up

ip link add link br0 name vlan10 type vlan id 10
ip link add link br0 name vlan20 type vlan id 20
ip link set vlan10 up
ip link set vlan20 up
