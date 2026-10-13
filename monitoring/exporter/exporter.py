"""Prometheus exporter for the data center lab.

One poller thread per device keeps an SSH session open (same Netmiko
automation layer as `python -m automation check`), collects BGP, interface,
PIM, mroute and IGMP state every POLL_INTERVAL seconds and caches it. Each
Prometheus scrape renders the cached state, so scrapes are fast and never
block on SSH.

Interfaces are labelled with the link they belong to, read from the
containerlab topology file, so dashboards can show "spine1:eth3 <-> leaf3:eth1"
instead of bare interface names.

    python -m monitoring.exporter.exporter --inventory inventory/frr-lab.yml \
        --topology topologies/dc-frr.clab.yml --port 9500
"""
from __future__ import annotations

import argparse
import logging
import re
import threading
import time
from pathlib import Path

import yaml
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, CounterMetricFamily, GaugeMetricFamily

from automation.collect import DeviceState, collect
from automation.connection import DeviceSession
from automation.inventory import Device, load_inventory

log = logging.getLogger("dclab-exporter")

COUNTERS = {
    "rx_bytes": "Bytes received",
    "tx_bytes": "Bytes transmitted",
    "rx_packets": "Packets received",
    "tx_packets": "Packets transmitted",
    "rx_errors": "Receive errors",
    "tx_errors": "Transmit errors",
    "rx_dropped": "Received packets dropped",
    "tx_dropped": "Transmitted packets dropped",
}


def load_links(topology: str | Path | None) -> dict[tuple[str, str], dict[str, str]]:
    """Map (node, interface) -> {link, peer, kind} from a containerlab topology."""
    if not topology:
        return {}
    topo = yaml.safe_load(Path(topology).read_text())
    nodes = topo["topology"]["nodes"]
    out: dict[tuple[str, str], dict[str, str]] = {}
    for link in topo["topology"].get("links", []):
        a, b = link["endpoints"]
        (na, ia), (nb, ib) = a.split(":"), b.split(":")
        roles = {(nodes.get(n) or {}).get("labels", {}).get("role", "") for n in (na, nb)}
        kind = "fabric" if roles == {"spine", "leaf"} else "access"
        name = f"{na}:{ia} <-> {nb}:{ib}"
        out[(na, ia)] = {"link": name, "peer": f"{nb}:{ib}", "kind": kind}
        out[(nb, ib)] = {"link": name, "peer": f"{na}:{ia}", "kind": kind}
    return out


def render(states: list[DeviceState], links: dict, exclude: re.Pattern,
           durations: dict[str, float] | None = None):
    """Turn cached device states into Prometheus metric families."""
    durations = durations or {}
    up = GaugeMetricFamily("dclab_device_up", "1 if the last poll of the device succeeded", labels=["device"])
    dur = GaugeMetricFamily("dclab_poll_duration_seconds", "Duration of the last poll", labels=["device"])
    ilabels = ["device", "interface", "link", "peer", "kind"]
    oper = GaugeMetricFamily("dclab_interface_oper_up", "Interface operational state (1 up, 0 down)", labels=ilabels)
    admin = GaugeMetricFamily("dclab_interface_admin_up", "Interface administrative state", labels=ilabels)
    counters = {k: CounterMetricFamily(f"dclab_interface_{k}", desc, labels=ilabels) for k, desc in COUNTERS.items()}
    blabels = ["device", "neighbor", "peer_name", "remote_as"]
    bgp_up = GaugeMetricFamily("dclab_bgp_session_established", "1 if the BGP session is Established", labels=blabels)
    bgp_pfx = GaugeMetricFamily("dclab_bgp_prefixes_received", "Prefixes received from the neighbor", labels=blabels)
    pim = GaugeMetricFamily("dclab_pim_neighbors", "Number of PIM neighbors", labels=["device"])
    mroutes = GaugeMetricFamily("dclab_mroutes", "Multicast routes (S,G and *,G) in the MRIB", labels=["device", "type"])
    igmp = GaugeMetricFamily("dclab_igmp_groups", "IGMP groups joined on host-facing interfaces", labels=["device"])

    for st in states:
        dev = st.name
        up.add_metric([dev], 1.0 if st.reachable and not st.errors else 0.0)
        if dev in durations:
            dur.add_metric([dev], durations[dev])
        for ifname, i in sorted((st.data.get("interfaces") or {}).items()):
            if exclude.search(ifname):
                continue
            meta = links.get((dev, ifname), {})
            lv = [dev, ifname, meta.get("link", f"{dev}:{ifname}"), meta.get("peer", ""), meta.get("kind", "internal")]
            oper.add_metric(lv, 1.0 if i["oper_up"] else 0.0)
            admin.add_metric(lv, 1.0 if i["admin_up"] else 0.0)
            for k, fam in counters.items():
                fam.add_metric(lv, float(i[k]))
        for ip, p in sorted((st.data.get("bgp") or {}).items()):
            lv = [dev, ip, p["description"], str(p["remote_as"])]
            bgp_up.add_metric(lv, 1.0 if p["established"] else 0.0)
            bgp_pfx.add_metric(lv, float(p["prefixes"]))
        if "pim_neighbors" in st.data:
            pim.add_metric([dev], float(len(st.data["pim_neighbors"])))
        if "mroutes" in st.data:
            sg = sum(1 for m in st.data["mroutes"] if m["source"] != "*")
            pim_star = sum(1 for m in st.data["mroutes"] if m["source"] == "*")
            mroutes.add_metric([dev, "sg"], float(sg))
            mroutes.add_metric([dev, "star_g"], float(pim_star))
        if "igmp_groups" in st.data:
            joined = [g for g in st.data["igmp_groups"] if not g["group"].startswith("224.0.")]
            igmp.add_metric([dev], float(len(joined)))

    yield from (up, dur, oper, admin, *counters.values(), bgp_up, bgp_pfx, pim, mroutes, igmp)


class Poller(threading.Thread):
    def __init__(self, device: Device, interval: float):
        super().__init__(name=f"poll-{device.name}", daemon=True)
        self.device = device
        self.interval = interval
        self.state = DeviceState(device.name, device.platform, errors={"connect": "not polled yet"})
        self.duration = 0.0
        self.session = DeviceSession(device)

    def poll_once(self) -> None:
        t0 = time.monotonic()
        state = collect(self.session)
        if state.errors:
            log.warning("%s: %s", self.device.name, state.errors)
            self.session.close()  # reconnect on the next cycle
        self.state, self.duration = state, time.monotonic() - t0

    def run(self) -> None:
        while True:
            try:
                self.poll_once()
            except Exception:  # keep the thread alive whatever happens
                log.exception("%s: poll failed", self.device.name)
                self.session.close()
            time.sleep(self.interval)


class LabCollector:
    def __init__(self, pollers: list[Poller], links: dict, exclude: re.Pattern):
        self.pollers, self.links, self.exclude = pollers, links, exclude

    def collect(self):
        states = [p.state for p in self.pollers]
        durations = {p.device.name: p.duration for p in self.pollers}
        yield from render(states, self.links, self.exclude, durations)


def main() -> None:
    ap = argparse.ArgumentParser(description="Data center lab Prometheus exporter")
    ap.add_argument("--inventory", default="inventory/frr-lab.yml")
    ap.add_argument("--topology", default="topologies/dc-frr.clab.yml")
    ap.add_argument("--port", type=int, default=9500)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--exclude", default=r"^(lo|eth0|pimreg|ipmr-lo)$", help="interface regex to skip")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    devices = load_inventory(args.inventory)
    pollers = [Poller(d, args.interval) for d in devices]
    REGISTRY.register(LabCollector(pollers, load_links(args.topology), re.compile(args.exclude)))
    for p in pollers:
        p.start()
    start_http_server(args.port)
    log.info("exporting %d devices on :%d every %.0fs", len(devices), args.port, args.interval)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
