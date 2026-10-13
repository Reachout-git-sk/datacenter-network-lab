"""SSH sessions to lab devices through Netmiko."""
from __future__ import annotations

from typing import Callable

from automation.inventory import Device
from automation.platforms import command


class DeviceSession:
    """Thin wrapper around a Netmiko connection that runs catalogue commands."""

    def __init__(self, device: Device, connect: Callable | None = None):
        self.device = device
        self._connect = connect
        self.conn = None

    def __enter__(self) -> "DeviceSession":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        if self.conn is None:
            connect = self._connect
            if connect is None:
                from netmiko import ConnectHandler  # imported lazily for unit tests
                connect = ConnectHandler
            self.conn = connect(**self.device.netmiko_params())

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.disconnect()
            finally:
                self.conn = None

    def run(self, key: str) -> str:
        """Run the catalogue command `key` for this device's platform."""
        return self.run_raw(command(self.device.platform, key))

    def run_raw(self, cmd: str) -> str:
        self.open()
        return self.conn.send_command(cmd, read_timeout=30, strip_prompt=True, strip_command=True)
