"""Inventory loading (YAML) with per-device defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PLATFORM_DEVICE_TYPES = {"frr": "linux", "eos": "arista_eos"}


@dataclass
class Device:
    name: str
    host: str
    platform: str
    device_type: str
    username: str
    password: str
    port: int = 22
    role: str = ""
    expect: dict[str, Any] = field(default_factory=dict)

    def netmiko_params(self) -> dict[str, Any]:
        return {
            "device_type": self.device_type,
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "fast_cli": False,
            "conn_timeout": 15,
        }


def load_inventory(path: str | Path, only: list[str] | None = None) -> list[Device]:
    data = yaml.safe_load(Path(path).read_text())
    defaults = data.get("defaults", {}) or {}
    devices = []
    for name, spec in (data.get("devices") or {}).items():
        if only and name not in only:
            continue
        merged = {**defaults, **(spec or {})}
        platform = merged.get("platform", "frr")
        if platform not in PLATFORM_DEVICE_TYPES:
            raise ValueError(f"{name}: unknown platform {platform!r}")
        devices.append(Device(
            name=name,
            host=str(merged["host"]),
            platform=platform,
            device_type=merged.get("device_type", PLATFORM_DEVICE_TYPES[platform]),
            username=merged["username"],
            password=str(merged["password"]),
            port=int(merged.get("port", 22)),
            role=merged.get("role", ""),
            expect={str(k): v for k, v in (merged.get("expect") or {}).items()},
        ))
    if only:
        missing = set(only) - {d.name for d in devices}
        if missing:
            raise ValueError(f"devices not in inventory: {', '.join(sorted(missing))}")
    return devices
