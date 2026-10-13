"""Collect and parse the state of one device (shared by `check` and the exporter)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from automation import parsers
from automation.connection import DeviceSession

# section name -> (catalogue command key, parser)
COLLECTORS = {
    "bgp": ("bgp_summary", parsers.parse_bgp_summary),
    "interfaces": ("interfaces", parsers.parse_interfaces),
    "pim_neighbors": ("pim_neighbors", parsers.parse_pim_neighbors),
    "mroutes": ("mroutes", parsers.parse_mroutes),
    "igmp_groups": ("igmp_groups", parsers.parse_igmp_groups),
}


@dataclass
class DeviceState:
    name: str
    platform: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def reachable(self) -> bool:
        return "connect" not in self.errors


def collect_from_outputs(name: str, platform: str, outputs: dict[str, str]) -> DeviceState:
    """Parse already-captured raw outputs (keyed by catalogue command name)."""
    state = DeviceState(name, platform)
    for section, (key, parser) in COLLECTORS.items():
        if key not in outputs:
            continue
        try:
            state.data[section] = parser(platform, outputs[key])
        except parsers.ParseError as exc:
            state.errors[section] = str(exc)
    return state


def collect(session: DeviceSession, sections: list[str] | None = None) -> DeviceState:
    """Run the commands for `sections` (default: all) and parse the results."""
    dev = session.device
    wanted = sections or list(COLLECTORS)
    try:
        session.open()
    except Exception as exc:  # netmiko raises several unrelated exception types
        state = DeviceState(dev.name, dev.platform)
        state.errors["connect"] = f"{type(exc).__name__}: {exc}"
        return state
    outputs: dict[str, str] = {}
    errors: dict[str, str] = {}
    for section in wanted:
        key = COLLECTORS[section][0]
        try:
            outputs[key] = session.run(key)
        except Exception as exc:
            errors[section] = f"{type(exc).__name__}: {exc}"
    state = collect_from_outputs(dev.name, dev.platform, outputs)
    state.errors.update(errors)
    return state
