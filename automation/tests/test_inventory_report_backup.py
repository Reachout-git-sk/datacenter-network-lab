import json
from datetime import datetime, timezone

import pytest

from automation import cli
from automation.backup import backup_device, backup_dir
from automation.checks import FAIL, PASS, Result
from automation.connection import DeviceSession
from automation.inventory import load_inventory
from automation.platforms import COMMANDS
from automation.report import render_json, render_text
from automation.tests.conftest import REPO, FakeConn, fixture_text


def test_frr_inventory_defaults_are_merged():
    devices = load_inventory(REPO / "inventory" / "frr-lab.yml")
    assert [d.name for d in devices] == ["spine1", "spine2", "leaf1", "leaf2", "leaf3"]
    assert all(d.device_type == "linux" and d.platform == "frr" for d in devices)
    assert devices[0].expect["bgp_neighbors"]["10.1.1.1"]["prefixes"] == 3


def test_ceos_inventory_mixes_platforms():
    devices = {d.name: d for d in load_inventory(REPO / "inventory" / "ceos-lab.yml")}
    assert devices["leaf1"].device_type == "arista_eos"
    assert devices["leaf1"].platform == "eos"
    assert devices["spine1"].device_type == "linux"
    assert devices["spine1"].username == "netops"
    assert devices["leaf1"].username == "admin"


def test_inventory_subset_and_unknown_device(tmp_path):
    inv = REPO / "inventory" / "frr-lab.yml"
    assert [d.name for d in load_inventory(inv, ["leaf2"])] == ["leaf2"]
    with pytest.raises(ValueError):
        load_inventory(inv, ["leaf7"])


def test_inventory_rejects_unknown_platform(tmp_path):
    bad = tmp_path / "inv.yml"
    bad.write_text("devices:\n  r1: {host: 1.1.1.1, platform: junos, username: a, password: b}\n")
    with pytest.raises(ValueError, match="unknown platform"):
        load_inventory(bad)


def test_every_platform_has_every_command():
    assert set(COMMANDS["frr"]) == set(COMMANDS["eos"])


def test_report_text_and_json():
    results = [Result("leaf1", "bgp_session", "10.1.1.0", PASS, "Established"),
               Result("leaf2", "interface", "eth1", FAIL, "admin down")]
    text = render_text(results)
    assert "1 passed, 1 failed -> FAILED" in text
    assert "leaf2   interface" in text
    data = json.loads(render_json(results))
    assert data["failed"] == 1 and data["results"][1]["detail"] == "admin down"


def test_backup_dir_is_timestamped(tmp_path):
    when = datetime(2026, 10, 13, 17, 3, 14, tzinfo=timezone.utc)
    assert backup_dir(tmp_path, when).name == "20261013T170314Z"


def test_backup_device_writes_clean_config(tmp_path):
    dev = load_inventory(REPO / "inventory" / "frr-lab.yml", ["leaf1"])[0]
    conn = FakeConn({COMMANDS["frr"]["running_config"]: fixture_text("frr/leaf1_running_config.txt")})
    with DeviceSession(dev, connect=lambda **_: conn) as s:
        path = backup_device(s, tmp_path / "snap")
    assert path.name == "leaf1.cfg"
    body = path.read_bytes()
    assert b"\r\n" not in body
    assert b"Building configuration" not in body
    assert b"hostname leaf1" in body


def test_cli_check_exit_codes(monkeypatch, capsys):
    """check returns 0 when healthy and 1 when something fails."""
    healthy = {
        COMMANDS["frr"]["bgp_summary"]: fixture_text("frr/leaf1_bgp_summary.json"),
        COMMANDS["frr"]["interfaces"]: fixture_text("frr/leaf1_ip_link.json"),
        COMMANDS["frr"]["pim_neighbors"]: fixture_text("frr/leaf1_pim_neighbor.json"),
    }
    broken = dict(healthy)
    broken[COMMANDS["frr"]["interfaces"]] = fixture_text("frr/leaf3_ip_link_eth1_shutdown.json")
    inv = str(REPO / "inventory" / "frr-lab.yml")

    for responses, code in ((healthy, 0), (broken, 1)):
        monkeypatch.setattr(DeviceSession, "open",
                            lambda self, r=responses: setattr(self, "conn", self.conn or FakeConn(r)))
        assert cli.main(["check", "-i", inv, "-d", "leaf1"]) == code
    out = capsys.readouterr().out
    assert "admin down" in out


def test_cli_bad_inventory_returns_2(tmp_path, capsys):
    assert cli.main(["check", "-i", str(tmp_path / "missing.yml")]) == 2
