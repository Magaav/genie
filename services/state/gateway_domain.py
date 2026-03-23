#!/usr/bin/env python3

from __future__ import annotations

from common import STATE_LAYOUT, file_summary, read_json_file, safe_int


def summary() -> dict:
    gateway_dir = STATE_LAYOUT["gateway_dir"]
    allowlist_file = gateway_dir / "telegram-allowlist.json"
    offset_file = gateway_dir / "telegram-update-offset.json"
    allowlist_payload = read_json_file(allowlist_file, {"allow_from": []})
    allow_from = allowlist_payload.get("allow_from", allowlist_payload.get("allowFrom", []))
    offset_payload = read_json_file(offset_file, {"offset": 0})
    return {
        "domain": "gateway",
        "dir": str(gateway_dir),
        "telegram_allowlist_file": file_summary(allowlist_file),
        "telegram_allowlist_size": len([item for item in allow_from if str(item).strip()]),
        "telegram_offset_file": file_summary(offset_file),
        "telegram_update_offset": max(0, safe_int(offset_payload.get("offset", 0))),
    }
