"""Health checks: compare collected device state with inventory expectations."""
from __future__ import annotations

from dataclasses import dataclass

from automation.collect import DeviceState

PASS, FAIL = "PASS", "FAIL"


@dataclass
class Result:
    device: str
    check: str
    target: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == PASS


def check_device(state: DeviceState, expect: dict) -> list[Result]:
    dev = state.name
    if not state.reachable:
        return [Result(dev, "reachability", "ssh", FAIL, state.errors["connect"])]
    results: list[Result] = [Result(dev, "reachability", "ssh", PASS, "connected")]
    results += check_bgp(state, expect.get("bgp_neighbors") or {})
    results += check_interfaces(state, expect.get("interfaces_up") or [])
    if "pim_neighbors" in expect:
        results += check_pim(state, int(expect["pim_neighbors"]))
    return results


def check_bgp(state: DeviceState, expected: dict) -> list[Result]:
    dev = state.name
    if not expected:
        return []
    if "bgp" not in state.data:
        return [Result(dev, "bgp_session", "all", FAIL, state.errors.get("bgp", "no BGP data"))]
    peers = state.data["bgp"]
    out = []
    for ip, exp in expected.items():
        exp = exp or {}
        label = f"{ip} ({exp['peer']})" if exp.get("peer") else ip
        p = peers.get(ip)
        if p is None:
            out.append(Result(dev, "bgp_session", label, FAIL, "neighbor not configured"))
            continue
        if not p["established"]:
            out.append(Result(dev, "bgp_session", label, FAIL, f"state {p['state']}"))
            continue
        out.append(Result(dev, "bgp_session", label, PASS, f"Established, AS {p['remote_as']}"))
        if "prefixes" in exp:
            want, got = int(exp["prefixes"]), p["prefixes"]
            status = PASS if got == want else FAIL
            out.append(Result(dev, "bgp_prefixes", label, status, f"received {got}, expected {want}"))
    return out


def check_interfaces(state: DeviceState, expected_up: list[str]) -> list[Result]:
    dev = state.name
    if not expected_up:
        return []
    if "interfaces" not in state.data:
        return [Result(dev, "interface", "all", FAIL, state.errors.get("interfaces", "no interface data"))]
    intfs = state.data["interfaces"]
    out = []
    for name in expected_up:
        i = intfs.get(name)
        if i is None:
            out.append(Result(dev, "interface", name, FAIL, "missing"))
        elif not i["admin_up"]:
            out.append(Result(dev, "interface", name, FAIL, "admin down"))
        elif not i["oper_up"]:
            out.append(Result(dev, "interface", name, FAIL, "admin up, oper down"))
        else:
            errs = i["rx_errors"] + i["tx_errors"]
            out.append(Result(dev, "interface", name, PASS, f"up, errors {errs}"))
    return out


def check_pim(state: DeviceState, expected: int) -> list[Result]:
    dev = state.name
    if "pim_neighbors" not in state.data:
        return [Result(dev, "pim_neighbors", "count", FAIL,
                       state.errors.get("pim_neighbors", "no PIM data"))]
    nbrs = state.data["pim_neighbors"]
    got = len(nbrs)
    status = PASS if got >= expected else FAIL
    where = ", ".join(f"{n['neighbor']}@{n['interface']}" for n in nbrs) or "none"
    return [Result(dev, "pim_neighbors", "count", status, f"{got} (expected {expected}): {where}")]


def summarize(results: list[Result]) -> tuple[int, int]:
    passed = sum(r.ok for r in results)
    return passed, len(results) - passed
