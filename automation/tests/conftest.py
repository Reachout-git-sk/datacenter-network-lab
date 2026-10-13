"""Shared helpers for the unit tests.

fixtures/frr/ holds real outputs captured from the running dc-frr lab
(vtysh JSON and `ip -j -s link`), including a capture taken while leaf3 eth1
was shut down. fixtures/eos/ holds hand-made samples that follow the Arista
eAPI JSON layout; they exercise the EOS code path until the cEOS lab can run
and real captures replace them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]


def fixture_text(rel: str) -> str:
    return (FIXTURES / rel).read_text()


class FakeConn:
    """Stands in for a Netmiko connection: maps command strings to canned output."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.sent: list[str] = []
        self.disconnected = False

    def send_command(self, cmd: str, **_kw) -> str:
        self.sent.append(cmd)
        if cmd not in self.responses:
            raise KeyError(f"unexpected command {cmd!r}")
        return self.responses[cmd]

    def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def fixture_loader():
    return fixture_text


@pytest.fixture
def repo_root() -> Path:
    return REPO
