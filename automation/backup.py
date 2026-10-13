"""Running-config backups into timestamped directories."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from automation.connection import DeviceSession
from automation.parsers import clean_running_config


def backup_dir(root: str | Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    return Path(root) / now.strftime("%Y%m%dT%H%M%SZ")


def backup_device(session: DeviceSession, dest: Path) -> Path:
    dev = session.device
    text = clean_running_config(dev.platform, session.run("running_config"))
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{dev.name}.cfg"
    with open(path, "w", newline="\n") as fh:
        fh.write(text)
    return path
