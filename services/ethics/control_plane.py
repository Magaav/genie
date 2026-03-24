#!/usr/bin/env python3

from __future__ import annotations


ALIASES = {
    "constitution": "policy",
    "review": "queue",
    "caps": "capabilities",
    "process": "process-queue",
}

HELP_TEXT = """Genie control plane:
/help
/status
/policy
/brain
/state
/capabilities
/backup
/run-checks
/propose <change request>
/queue
/confirm <proposal-id>
/process-queue

Safe commands run directly.
High-impact evolution requests become proposals and are kept reviewable.
Confirmed low-risk proposals can be processed by the bounded workcell path."""


def parse_control_command(text: str) -> dict | None:
    stripped = str(text or "").strip()
    if not stripped.startswith("/"):
        return None
    first_line = stripped.splitlines()[0]
    parts = first_line.split(None, 1)
    command = parts[0][1:].strip().lower()
    command = ALIASES.get(command, command)
    argument = parts[1].strip() if len(parts) > 1 else ""
    return {"command": command, "argument": argument}


def format_queue(records: list[dict]) -> str:
    if not records:
        return "No queued proposals."
    lines: list[str] = []
    for item in records:
        proposal_id = str(item.get("id", "proposal-unknown"))
        status = str(item.get("status", "queued"))
        confirmed = " confirmed" if item.get("operator_confirmed") else ""
        review = " frontier-review" if item.get("frontier_review_required") else ""
        text = str(item.get("text", "")).strip().replace("\n", " ")
        if len(text) > 88:
            text = text[:85] + "..."
        lines.append(f"{proposal_id} [{status}{confirmed}{review}] {text}")
    return "\n".join(lines)
