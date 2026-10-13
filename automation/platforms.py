"""Per-platform command catalogue.

FRR nodes are reached over SSH as a Linux shell (Netmiko "linux"); routing
state comes from vtysh in JSON form and interface counters from iproute2.
Arista EOS nodes (Netmiko "arista_eos") use the native CLI with "| json".
"""
from __future__ import annotations

COMMANDS = {
    "frr": {
        "running_config": "vtysh -c 'show running-config'",
        "bgp_summary": "vtysh -c 'show bgp ipv4 unicast summary json'",
        "interfaces": "ip -j -s link show",
        "pim_neighbors": "vtysh -c 'show ip pim neighbor json'",
        "mroutes": "vtysh -c 'show ip mroute json'",
        "igmp_groups": "vtysh -c 'show ip igmp groups json'",
    },
    "eos": {
        "running_config": "show running-config",
        "bgp_summary": "show ip bgp summary | json",
        "interfaces": "show interfaces | json",
        "pim_neighbors": "show ip pim neighbor | json",
        "mroutes": "show ip mroute | json",
        "igmp_groups": "show ip igmp groups | json",
    },
}


def command(platform: str, key: str) -> str:
    try:
        return COMMANDS[platform][key]
    except KeyError as exc:
        raise ValueError(f"no {key!r} command for platform {platform!r}") from exc
