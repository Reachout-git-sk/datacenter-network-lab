import pytest

from automation import parsers
from automation.tests.conftest import fixture_text


# ------------------------------------------------------------------ FRR / BGP

def test_frr_bgp_summary_leaf_has_two_established_spines():
    peers = parsers.parse_bgp_summary("frr", fixture_text("frr/leaf1_bgp_summary.json"))
    assert set(peers) == {"10.1.1.0", "10.1.2.0"}
    for p in peers.values():
        assert p["established"] is True
        assert p["prefixes"] == 7
        assert p["remote_as"] == 65000
    assert peers["10.1.1.0"]["description"] == "spine1"


def test_frr_bgp_summary_spine_sees_three_leaves():
    peers = parsers.parse_bgp_summary("frr", fixture_text("frr/spine1_bgp_summary.json"))
    assert {p["remote_as"] for p in peers.values()} == {65101, 65102, 65103}
    assert all(p["prefixes"] == 3 for p in peers.values())


def test_frr_bgp_summary_session_down_reports_state_and_zero_prefixes():
    peers = parsers.parse_bgp_summary("frr", fixture_text("frr/spine1_bgp_summary_leaf3_down.json"))
    leaf3 = peers["10.1.1.5"]
    assert leaf3["established"] is False
    assert leaf3["state"] == "Active"
    assert leaf3["prefixes"] == 0
    assert peers["10.1.1.1"]["established"] is True


def test_frr_bgp_summary_accepts_wrapped_afi_form():
    wrapped = '{"ipv4Unicast": {"peers": {"10.0.0.9": {"state": "Idle", "remoteAs": 1}}}}'
    peers = parsers.parse_bgp_summary("frr", wrapped)
    assert peers["10.0.0.9"]["state"] == "Idle"


# ----------------------------------------------------------- FRR / interfaces

def test_frr_interfaces_up_with_counters():
    intfs = parsers.parse_interfaces("frr", fixture_text("frr/leaf1_ip_link.json"))
    for name in ("eth1", "eth2", "eth3", "eth4", "br0", "vlan10", "vlan20"):
        assert intfs[name]["admin_up"] and intfs[name]["oper_up"], name
    assert intfs["eth1"]["rx_packets"] > 0
    assert isinstance(intfs["eth1"]["tx_bytes"], int)


def test_frr_interface_admin_shutdown():
    intfs = parsers.parse_interfaces("frr", fixture_text("frr/leaf3_ip_link_eth1_shutdown.json"))
    assert intfs["eth1"]["admin_up"] is False
    assert intfs["eth1"]["oper_up"] is False
    assert intfs["eth2"]["oper_up"] is True


def test_frr_interface_peer_down_is_admin_up_oper_down():
    intfs = parsers.parse_interfaces("frr", fixture_text("frr/spine1_ip_link_eth3_peer_down.json"))
    assert intfs["eth3"]["admin_up"] is True
    assert intfs["eth3"]["oper_up"] is False


# ------------------------------------------------------------ FRR / multicast

def test_frr_pim_neighbors():
    leaf = parsers.parse_pim_neighbors("frr", fixture_text("frr/leaf1_pim_neighbor.json"))
    assert leaf == [{"interface": "eth1", "neighbor": "10.1.1.0"},
                    {"interface": "eth2", "neighbor": "10.1.2.0"}]
    spine = parsers.parse_pim_neighbors("frr", fixture_text("frr/spine1_pim_neighbor.json"))
    assert len(spine) == 3


def test_frr_mroutes_shared_and_source_trees():
    mroutes = parsers.parse_mroutes("frr", fixture_text("frr/leaf2_mroute.json"))
    by_src = {m["source"]: m for m in mroutes}
    assert set(by_src) == {"*", "10.10.1.10"}
    assert all(m["group"] == "239.1.1.1" and m["installed"] for m in mroutes)
    assert by_src["*"]["iif"] == "eth1"


def test_frr_igmp_groups_subscriber_joined():
    groups = parsers.parse_igmp_groups("frr", fixture_text("frr/leaf2_igmp_groups.json"))
    assert {"interface": "vlan10", "group": "239.1.1.1"} in groups


# ------------------------------------------------------------------- EOS

def test_eos_bgp_summary():
    peers = parsers.parse_bgp_summary("eos", fixture_text("eos/leaf1_bgp_summary.json"))
    assert peers["10.1.1.0"]["established"] and peers["10.1.1.0"]["prefixes"] == 7
    assert peers["10.1.2.0"]["state"] == "Active"
    assert peers["10.1.1.0"]["remote_as"] == 65000


def test_eos_interfaces():
    intfs = parsers.parse_interfaces("eos", fixture_text("eos/leaf1_interfaces.json"))
    assert intfs["Ethernet1"]["oper_up"] and intfs["Ethernet1"]["rx_packets"] == 1210
    assert intfs["Ethernet2"]["admin_up"] is False
    assert intfs["Ethernet2"]["rx_errors"] == 3
    assert intfs["Vlan10"]["oper_up"] and intfs["Vlan10"]["rx_bytes"] == 0


def test_eos_pim_and_mroute():
    nbrs = parsers.parse_pim_neighbors("eos", fixture_text("eos/leaf1_pim_neighbor.json"))
    assert nbrs == [{"interface": "Ethernet1", "neighbor": "10.1.1.0"}]
    mroutes = parsers.parse_mroutes("eos", fixture_text("eos/leaf2_mroute.json"))
    assert [m["source"] for m in mroutes] == ["*", "10.10.1.10"]


# ------------------------------------------------------------------ misc

def test_json_after_echoed_noise_is_found():
    assert parsers._load_json("vtysh -c x\n{\"a\": 1}") == {"a": 1}


@pytest.mark.parametrize("bad", ["", "   ", "% Unknown command", "{not json"])
def test_bad_output_raises_parse_error(bad):
    with pytest.raises(parsers.ParseError):
        parsers.parse_bgp_summary("frr", bad)


def test_unknown_platform():
    with pytest.raises(parsers.ParseError):
        parsers.parse_bgp_summary("junos", "{}")


def test_clean_running_config_frr():
    text = parsers.clean_running_config("frr", fixture_text("frr/leaf1_running_config.txt"))
    assert not text.startswith("Building configuration")
    assert "Current configuration:" not in text
    assert "router bgp 65101" in text
    assert text.endswith("\n")


def test_clean_running_config_eos_drops_timestamp():
    text = parsers.clean_running_config("eos", fixture_text("eos/leaf1_running_config.txt"))
    assert "! Time:" not in text
    assert "hostname leaf1" in text
