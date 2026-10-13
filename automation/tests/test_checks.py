from automation.checks import FAIL, PASS, check_device, summarize
from automation.collect import DeviceState, collect, collect_from_outputs
from automation.connection import DeviceSession
from automation.inventory import load_inventory
from automation.platforms import command
from automation.tests.conftest import REPO, FakeConn, fixture_text


def _inventory():
    return {d.name: d for d in load_inventory(REPO / "inventory" / "frr-lab.yml")}


def _state(name, bgp, links, pim):
    return collect_from_outputs(name, "frr", {
        "bgp_summary": fixture_text(bgp),
        "interfaces": fixture_text(links),
        "pim_neighbors": fixture_text(pim),
    })


def test_healthy_leaf_passes_everything():
    dev = _inventory()["leaf1"]
    state = _state("leaf1", "frr/leaf1_bgp_summary.json", "frr/leaf1_ip_link.json",
                   "frr/leaf1_pim_neighbor.json")
    results = check_device(state, dev.expect)
    passed, failed = summarize(results)
    assert failed == 0, [r for r in results if not r.ok]
    # reachability + 2x(session, prefixes) + 7 interfaces + pim
    assert passed == 1 + 4 + 7 + 1


def test_spine_with_leaf3_link_down_fails_session_link_and_pim():
    dev = _inventory()["spine1"]
    state = _state("spine1", "frr/spine1_bgp_summary_leaf3_down.json",
                   "frr/spine1_ip_link_eth3_peer_down.json", "frr/leaf1_pim_neighbor.json")
    results = check_device(state, dev.expect)
    failed = {(r.check, r.target) for r in results if r.status == FAIL}
    assert ("bgp_session", "10.1.1.5 (leaf3)") in failed
    assert ("interface", "eth3") in failed
    assert ("pim_neighbors", "count") in failed
    # the two healthy sessions still pass
    ok = {(r.check, r.target) for r in results if r.status == PASS}
    assert ("bgp_session", "10.1.1.1 (leaf1)") in ok
    detail = next(r.detail for r in results if r.target == "eth3")
    assert detail == "admin up, oper down"


def test_prefix_count_mismatch_is_a_failure():
    state = _state("leaf1", "frr/leaf1_bgp_summary.json", "frr/leaf1_ip_link.json",
                   "frr/leaf1_pim_neighbor.json")
    expect = {"bgp_neighbors": {"10.1.1.0": {"peer": "spine1", "prefixes": 9}}}
    results = check_device(state, expect)
    bad = [r for r in results if not r.ok]
    assert len(bad) == 1 and bad[0].check == "bgp_prefixes"
    assert bad[0].detail == "received 7, expected 9"


def test_missing_neighbor_and_interface():
    state = _state("leaf1", "frr/leaf1_bgp_summary.json", "frr/leaf1_ip_link.json",
                   "frr/leaf1_pim_neighbor.json")
    expect = {"bgp_neighbors": {"192.0.2.1": None}, "interfaces_up": ["eth9"]}
    details = {r.target: r.detail for r in check_device(state, expect) if not r.ok}
    assert details == {"192.0.2.1": "neighbor not configured", "eth9": "missing"}


def test_unreachable_device_is_single_failure():
    state = DeviceState("leaf9", "frr", errors={"connect": "NetmikoTimeoutException: timed out"})
    results = check_device(state, {"pim_neighbors": 2})
    assert len(results) == 1 and results[0].status == FAIL


def test_parse_error_surfaces_as_failure():
    state = collect_from_outputs("leaf1", "frr", {"bgp_summary": "% Unknown command"})
    results = check_device(state, {"bgp_neighbors": {"10.1.1.0": {}}})
    assert results[-1].status == FAIL and "JSON" in results[-1].detail


def test_collect_over_fake_netmiko_session():
    dev = _inventory()["leaf1"]
    responses = {
        command("frr", "bgp_summary"): fixture_text("frr/leaf1_bgp_summary.json"),
        command("frr", "interfaces"): fixture_text("frr/leaf1_ip_link.json"),
        command("frr", "pim_neighbors"): fixture_text("frr/leaf1_pim_neighbor.json"),
    }
    conn = FakeConn(responses)
    seen = {}

    def connect(**params):
        seen.update(params)
        return conn

    with DeviceSession(dev, connect=connect) as session:
        state = collect(session, ["bgp", "interfaces", "pim_neighbors"])
    assert seen["device_type"] == "linux" and seen["host"] == "172.30.30.21"
    assert conn.disconnected
    assert conn.sent[0] == "vtysh -c 'show bgp ipv4 unicast summary json'"
    assert summarize(check_device(state, dev.expect))[1] == 0


def test_collect_records_connect_errors():
    dev = _inventory()["leaf1"]

    def connect(**_):
        raise TimeoutError("no route to host")

    state = collect(DeviceSession(dev, connect=connect))
    assert not state.reachable
    assert "TimeoutError" in state.errors["connect"]
