#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import json

from common import STATE_LAYOUT, directory_summary, file_summary


def summary() -> dict:
    runtime_dir = STATE_LAYOUT["runtime_dir"]
    queue_file = STATE_LAYOUT["runtime_review_queue_file"]
    control_log_file = STATE_LAYOUT["runtime_control_log_file"]
    proposals = _read_jsonl(queue_file)
    return {
        "domain": "runtime",
        "dir": str(runtime_dir),
        "packages": directory_summary(STATE_LAYOUT["runtime_packages_dir"], recent_limit=3),
        "responses": directory_summary(STATE_LAYOUT["runtime_responses_dir"], recent_limit=3),
        "bridge": directory_summary(STATE_LAYOUT["runtime_bridge_dir"], recent_limit=3),
        "frontier": directory_summary(STATE_LAYOUT["runtime_frontier_dir"], recent_limit=3),
        "workcells": directory_summary(STATE_LAYOUT["runtime_workcells_dir"], recent_limit=5),
        "review_queue_file": {
            **file_summary(queue_file),
            "records": len(proposals),
            "queued": sum(1 for item in proposals if item.get("status") == "queued"),
            "confirmed": sum(1 for item in proposals if item.get("operator_confirmed")),
            "processing": sum(1 for item in proposals if item.get("status") == "processing"),
            "applied_safe": sum(1 for item in proposals if item.get("status") == "applied_safe"),
            "draft_ready": sum(1 for item in proposals if item.get("status") == "draft_ready"),
        },
        "control_log_file": {
            **file_summary(control_log_file),
            "records": len(_read_jsonl(control_log_file)),
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _write_jsonl(path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _next_id(prefix: str, records: list[dict]) -> str:
    max_value = 0
    for record in records:
        raw_id = str(record.get("id", ""))
        if not raw_id.startswith(f"{prefix}-"):
            continue
        try:
            max_value = max(max_value, int(raw_id.split("-")[-1]))
        except ValueError:
            continue
    return f"{prefix}-{max_value + 1:06d}"


def create_proposal(payload: dict) -> dict:
    queue_file = STATE_LAYOUT["runtime_review_queue_file"]
    records = _read_jsonl(queue_file)
    proposal = {
        "id": _next_id("proposal", records),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "status": str(payload.get("status", "queued")).strip() or "queued",
        "operator_confirmed": bool(payload.get("operator_confirmed", False)),
        "frontier_review_required": bool(payload.get("frontier_review_required", False)),
        "source": str(payload.get("source", "unknown")).strip() or "unknown",
        "channel": str(payload.get("channel", "control")).strip() or "control",
        "user_id": str(payload.get("user_id", "")).strip(),
        "chat_id": str(payload.get("chat_id", "")).strip(),
        "text": str(payload.get("text", "")).strip(),
        "risk_class": str(payload.get("risk_class", "unknown")).strip() or "unknown",
        "complexity_class": str(payload.get("complexity_class", "medium")).strip() or "medium",
        "policy_tags": payload.get("policy_tags", []),
        "instinct": payload.get("instinct", {}),
    }
    records.append(proposal)
    _write_jsonl(queue_file, records)
    return {
        "ok": True,
        "proposal": proposal,
        "queue_file": str(queue_file),
        "queue_size": len(records),
    }


def list_proposals(payload: dict) -> dict:
    queue_file = STATE_LAYOUT["runtime_review_queue_file"]
    records = _read_jsonl(queue_file)
    status_filter = str(payload.get("status", "")).strip().lower()
    if status_filter:
        records = [record for record in records if str(record.get("status", "")).strip().lower() == status_filter]
    limit = max(1, min(50, int(payload.get("limit", 10) or 10)))
    records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {
        "ok": True,
        "queue_file": str(queue_file),
        "records": records[:limit],
        "total": len(records),
    }


def confirm_proposal(payload: dict) -> dict:
    proposal_id = str(payload.get("proposal_id", "")).strip()
    if not proposal_id:
        raise ValueError("proposal_id is required")
    queue_file = STATE_LAYOUT["runtime_review_queue_file"]
    records = _read_jsonl(queue_file)
    updated_record = None
    for record in records:
        if str(record.get("id", "")) != proposal_id:
            continue
        record["operator_confirmed"] = True
        record["status"] = str(payload.get("status", "confirmed")).strip() or "confirmed"
        record["confirmed_at"] = _utc_now()
        record["confirmed_by"] = str(payload.get("confirmed_by", "operator")).strip() or "operator"
        record["updated_at"] = _utc_now()
        updated_record = record
        break
    if updated_record is None:
        raise ValueError(f"proposal not found: {proposal_id}")
    _write_jsonl(queue_file, records)
    return {
        "ok": True,
        "proposal": updated_record,
        "queue_file": str(queue_file),
    }


def update_proposal(payload: dict) -> dict:
    proposal_id = str(payload.get("proposal_id", "")).strip()
    if not proposal_id:
        raise ValueError("proposal_id is required")
    updates = payload.get("updates", {})
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates is required")
    queue_file = STATE_LAYOUT["runtime_review_queue_file"]
    records = _read_jsonl(queue_file)
    updated_record = None
    for record in records:
        if str(record.get("id", "")) != proposal_id:
            continue
        for key, value in updates.items():
            record[key] = value
        record["updated_at"] = _utc_now()
        updated_record = record
        break
    if updated_record is None:
        raise ValueError(f"proposal not found: {proposal_id}")
    _write_jsonl(queue_file, records)
    return {"ok": True, "proposal": updated_record, "queue_file": str(queue_file)}


def append_control_log(payload: dict) -> dict:
    log_file = STATE_LAYOUT["runtime_control_log_file"]
    records = _read_jsonl(log_file)
    record = {
        "id": _next_id("control", records),
        "created_at": _utc_now(),
        "event": str(payload.get("event", "unknown")).strip() or "unknown",
        "source": str(payload.get("source", "unknown")).strip() or "unknown",
        "user_id": str(payload.get("user_id", "")).strip(),
        "chat_id": str(payload.get("chat_id", "")).strip(),
        "command": str(payload.get("command", "")).strip(),
        "details": payload.get("details", {}),
    }
    records.append(record)
    _write_jsonl(log_file, records)
    return {
        "ok": True,
        "record": record,
        "log_file": str(log_file),
        "records": len(records),
    }
