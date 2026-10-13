import re

from automation.collect import DeviceState, collect_from_outputs
from automation.tests.conftest import REPO, fixture_text
from monitoring.exporter.exporter import load_links, render

EXCLUDE = re.compile(r"^(lo|eth0|pimreg)$")


def _samples(families):
    out = {}
    for fam in families:
        for s in fam.samples:
            out.setdefault(s.name, []).append(s)
    return out


def test_links_from_topology():
    links = load_links(REPO / "topologies" / "dc-frr.clab.yml")
    assert links[("spine1", "eth3")] == {"link": "spine1:eth3 <-> leaf3:eth1", "peer": "leaf3:eth1", "kind": "fabric"}
    assert links[("leaf3", "eth1")]["peer"] == "spine1:eth3"
    assert links[("leaf1", "eth3")]["kind"] == "access"
    assert sum(1 for v in links.values() if v["kind"] == "fabric") == 12


def test_render_link_down_and_bgp_state():
    spine = collect_from_outputs("spine1", "frr", {
        "bgp_summary": fixture_text("frr/spine1_bgp_summary_leaf3_down.json"),
        "interfaces": fixture_text("frr/spine1_ip_link_eth3_peer_down.json"),
        "pim_neighbors": fixture_text("frr/leaf1_pim_neighbor.json"),
    })
    leaf2 = collect_from_outputs("leaf2", "frr", {
        "mroutes": fixture_text("frr/leaf2_mroute.json"),
        "igmp_groups": fixture_text("frr/leaf2_igmp_groups.json"),
    })
    links = load_links(REPO / "topologies" / "dc-frr.clab.yml")
    s = _samples(render([spine, leaf2], links, EXCLUDE, {"spine1": 0.4}))

    oper = {x.labels["interface"]: x.value for x in s["dclab_interface_oper_up"] if x.labels["device"] == "spine1"}
    assert oper["eth3"] == 0.0 and oper["eth1"] == 1.0
    assert "eth0" not in oper and "lo" not in oper
    eth3 = next(x for x in s["dclab_interface_oper_up"] if x.labels["interface"] == "eth3")
    assert eth3.labels["link"] == "spine1:eth3 <-> leaf3:eth1"

    bgp = {x.labels["neighbor"]: x.value for x in s["dclab_bgp_session_established"]}
    assert bgp == {"10.1.1.1": 1.0, "10.1.1.3": 1.0, "10.1.1.5": 0.0}
    assert {x.labels["peer_name"] for x in s["dclab_bgp_prefixes_received"]} == {"leaf1", "leaf2", "leaf3"}

    rx = [x for x in s["dclab_interface_rx_bytes_total"] if x.labels["interface"] == "eth1"]
    assert rx and rx[0].value > 0

    mr = {x.labels["type"]: x.value for x in s["dclab_mroutes"]}
    assert mr == {"sg": 1.0, "star_g": 1.0}
    assert s["dclab_igmp_groups"][0].value == 1.0      # 239.1.1.1; 224.0.1.40 ignored
    assert s["dclab_pim_neighbors"][0].value == 2.0


def test_unreachable_device_reports_down():
    st = DeviceState("leaf9", "frr", errors={"connect": "timeout"})
    s = _samples(render([st], {}, EXCLUDE))
    assert s["dclab_device_up"][0].value == 0.0
    assert "dclab_interface_oper_up" not in s
