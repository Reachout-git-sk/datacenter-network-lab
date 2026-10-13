"""Plain-text and JSON rendering of check results."""
from __future__ import annotations

import json
from dataclasses import asdict

from automation.checks import Result, summarize

HEADERS = ("DEVICE", "CHECK", "TARGET", "STATUS", "DETAIL")


def render_text(results: list[Result], title: str = "Fabric health check") -> str:
    rows = [(r.device, r.check, r.target, r.status, r.detail) for r in results]
    widths = [max([len(h)] + [len(row[i]) for row in rows]) for i, h in enumerate(HEADERS[:-1])]
    fmt = "  ".join("{:<%d}" % w for w in widths) + "  {}"
    lines = [title, "=" * len(title), fmt.format(*HEADERS),
             fmt.format(*["-" * w for w in widths], "-" * 6)]
    prev = None
    for row in rows:
        if prev is not None and row[0] != prev:
            lines.append("")
        lines.append(fmt.format(*row))
        prev = row[0]
    passed, failed = summarize(results)
    verdict = "OK" if failed == 0 else "FAILED"
    lines += ["", f"{passed} passed, {failed} failed -> {verdict}"]
    return "\n".join(lines) + "\n"


def render_json(results: list[Result]) -> str:
    passed, failed = summarize(results)
    return json.dumps({"passed": passed, "failed": failed,
                       "results": [asdict(r) for r in results]}, indent=2) + "\n"
