"""Parsers that turn raw device output into platform-neutral dictionaries.

Every parser takes the platform name and the raw text returned over SSH, and
returns plain dicts/lists so the check logic and the exporter never need to
know which vendor they are talking to.
"""
from __future__ import annotations

import json
import re
from typing import Any


class ParseError(ValueError):
    pass


def _load_json(text: str) -> Any:
    """Load JSON from CLI output, tolerating banner/echo lines before it."""
    text = text.strip()
    if not text:
        raise ParseError("empty output")
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ParseError(f"no JSON in output: {text[:80]!r}")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc


# --------------------------------------------------------------------- BGP

def parse_bgp_summary(platform: str, text: str) -> dict[str, dict[str, Any]]:
    """Return {peer_ip: {state, established, prefixes, remote_as, description}}."""
    data = _load_json(text)
    peers: dict[str, dict[str, Any]] = {}
    if platform == "frr":
        if "ipv4Unicast" in data:  # "show bgp summary json" wraps per AFI/SAFI
            data = data["ipv4Unicast"]
        for ip, p in (data.get("peers") or {}).items():
            state = p.get("state", "Unknown")
            peers[ip] = {
                "state": state,
                "established": state == "Established",
                "prefixes": int(p.get("pfxRcd", 0)) if state == "Established" else 0,
                "remote_as": int(p.get("remoteAs", 0)),
                "description": p.get("desc") or p.get("hostname", ""),
            }
    elif platform == "eos":
        vrf = (data.get("vrfs") or {}).get("default", {})
        for ip, p in (vrf.get("peers") or {}).items():
            state = p.get("peerState", "Unknown")
            peers[ip] = {
                "state": state,
                "established": state == "Established",
                "prefixes": int(p.get("prefixAccepted", p.get("prefixReceived", 0))),
                "remote_as": int(p.get("asn", 0)),
                "description": p.get("description", ""),
            }
    else:
        raise ParseError(f"unsupported platform {platform!r}")
    return peers


# --------------------------------------------------------------- interfaces

def parse_interfaces(platform: str, text: str) -> dict[str, dict[str, Any]]:
    """Return {ifname: {admin_up, oper_up, rx/tx bytes/packets/errors/drops}}."""
    data = _load_json(text)
    out: dict[str, dict[str, Any]] = {}
    if platform == "frr":
        # iproute2: ip -j -s link show
        for link in data:
            flags = set(link.get("flags", []))
            stats = link.get("stats64") or link.get("stats") or {}
            rx, tx = stats.get("rx", {}), stats.get("tx", {})
            name = link["ifname"]
            out[name] = {
                "admin_up": "UP" in flags,
                # a veth whose peer went down keeps UP but loses LOWER_UP
                "oper_up": "UP" in flags and "LOWER_UP" in flags,
                "rx_bytes": rx.get("bytes", 0),
                "tx_bytes": tx.get("bytes", 0),
                "rx_packets": rx.get("packets", 0),
                "tx_packets": tx.get("packets", 0),
                "rx_errors": rx.get("errors", 0),
                "tx_errors": tx.get("errors", 0),
                "rx_dropped": rx.get("dropped", 0),
                "tx_dropped": tx.get("dropped", 0),
            }
    elif platform == "eos":
        for name, intf in (data.get("interfaces") or {}).items():
            c = intf.get("interfaceCounters") or {}
            out[name] = {
                "admin_up": intf.get("interfaceStatus") != "disabled",
                "oper_up": intf.get("lineProtocolStatus") == "up",
                "rx_bytes": c.get("inOctets", 0),
                "tx_bytes": c.get("outOctets", 0),
                "rx_packets": sum(c.get(k, 0) for k in ("inUcastPkts", "inMulticastPkts", "inBroadcastPkts")),
                "tx_packets": sum(c.get(k, 0) for k in ("outUcastPkts", "outMulticastPkts", "outBroadcastPkts")),
                "rx_errors": c.get("totalInErrors", 0),
                "tx_errors": c.get("totalOutErrors", 0),
                "rx_dropped": c.get("inDiscards", 0),
                "tx_dropped": c.get("outDiscards", 0),
            }
    else:
        raise ParseError(f"unsupported platform {platform!r}")
    return out


# ---------------------------------------------------------------------- PIM

def parse_pim_neighbors(platform: str, text: str) -> list[dict[str, str]]:
    """Return [{interface, neighbor}]."""
    data = _load_json(text)
    out: list[dict[str, str]] = []
    if platform == "frr":
        # {ifname: {neighbor_ip: {...}}}
        for ifname, nbrs in data.items():
            if not isinstance(nbrs, dict):
                continue
            for ip, n in nbrs.items():
                out.append({"interface": n.get("interface", ifname), "neighbor": n.get("neighbor", ip)})
    elif platform == "eos":
        vrf = (data.get("vrfs") or {}).get("default", data)
        for ip, n in (vrf.get("neighbors") or {}).items():
            out.append({"interface": n.get("interface", ""), "neighbor": ip})
    else:
        raise ParseError(f"unsupported platform {platform!r}")
    return sorted(out, key=lambda n: (n["interface"], n["neighbor"]))


def parse_mroutes(platform: str, text: str) -> list[dict[str, Any]]:
    """Return [{source, group, iif, installed}] ("*" for shared-tree entries)."""
    data = _load_json(text)
    out: list[dict[str, Any]] = []
    if platform == "frr":
        for group, sources in data.items():
            if not isinstance(sources, dict):
                continue
            for src, e in sources.items():
                out.append({
                    "source": e.get("source", src),
                    "group": e.get("group", group),
                    "iif": e.get("iif", ""),
                    "installed": bool(e.get("installed", 0)),
                })
    elif platform == "eos":
        vrf = (data.get("vrfs") or {}).get("default", data)
        for group, g in (vrf.get("groups") or {}).items():
            for src, e in (g.get("groupSources") or {}).items():
                out.append({
                    "source": "*" if src in ("0.0.0.0", "*") else src,
                    "group": group,
                    "iif": e.get("rpfInterface", ""),
                    "installed": True,
                })
    else:
        raise ParseError(f"unsupported platform {platform!r}")
    return sorted(out, key=lambda m: (m["group"], m["source"]))


def parse_igmp_groups(platform: str, text: str) -> list[dict[str, str]]:
    """Return [{interface, group}] for groups joined by hosts."""
    data = _load_json(text)
    out: list[dict[str, str]] = []
    if platform == "frr":
        for ifname, entry in data.items():
            if not isinstance(entry, dict):
                continue
            for g in entry.get("groups", []):
                out.append({"interface": ifname, "group": g["group"]})
    elif platform == "eos":
        for g in data.get("groupList") or []:
            out.append({"interface": g.get("interfaceName", ""), "group": g["groupAddress"]})
    else:
        raise ParseError(f"unsupported platform {platform!r}")
    return sorted(out, key=lambda g: (g["interface"], g["group"]))


# ----------------------------------------------------------------- config

_FRR_NOISE = re.compile(r"^(Building configuration\.\.\.|Current configuration:)\s*$")


def clean_running_config(platform: str, text: str) -> str:
    """Strip CLI preamble so backups diff cleanly."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    if platform == "frr":
        lines = [ln for ln in lines if not _FRR_NOISE.match(ln)]
    elif platform == "eos":
        lines = [ln for ln in lines if not ln.startswith("! Time:")]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines) + "\n"
