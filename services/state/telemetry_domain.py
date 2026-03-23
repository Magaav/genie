#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

from common import STATE_LAYOUT, count_by, file_summary, read_json_file


def _usage_ledger_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["telemetry_dir"] / "provider-usage.jsonl"
    lines = 0
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                lines = sum(1 for _ in handle if _.strip())
        except OSError:
            lines = 0
    return {
        **file_summary(path),
        "records": lines,
    }


def _health_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["telemetry_dir"] / "provider-health.json"
    payload = read_json_file(path, {})
    providers = payload.get("providers", {}) if isinstance(payload, dict) else {}
    provider_rows = [value for value in providers.values() if isinstance(value, dict)]
    return {
        **file_summary(path),
        "provider_count": len(providers),
        "health_state_counts": count_by(provider_rows, "state", "unknown"),
    }


def _benchmarks_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["telemetry_dir"] / "provider-benchmarks.json"
    payload = read_json_file(path, {})
    benchmarks = payload.get("benchmarks", {}) if isinstance(payload, dict) else {}
    return {
        **file_summary(path),
        "provider_count": len(benchmarks),
    }


def _scorecards_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["telemetry_dir"] / "provider-scorecards.json"
    payload = read_json_file(path, {})
    scorecards = payload.get("providers", {}) if isinstance(payload, dict) else {}
    return {
        **file_summary(path),
        "provider_count": len(scorecards),
    }


def _discovery_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["telemetry_dir"] / "provider-discovery.json"
    payload = read_json_file(path, {})
    providers = payload.get("providers", {}) if isinstance(payload, dict) else {}
    provider_rows = [value for value in providers.values() if isinstance(value, dict)]
    return {
        **file_summary(path),
        "provider_count": len(providers),
        "provider_family_counts": count_by(provider_rows, "provider_family"),
        "state_counts": count_by(provider_rows, "brain_router_state", "unknown"),
    }


def summary() -> dict[str, Any]:
    telemetry_dir = STATE_LAYOUT["telemetry_dir"]
    return {
        "domain": "telemetry",
        "dir": str(telemetry_dir),
        "files": {
            "provider_usage": _usage_ledger_summary(),
            "provider_health": _health_summary(),
            "provider_benchmarks": _benchmarks_summary(),
            "provider_scorecards": _scorecards_summary(),
            "provider_discovery": _discovery_summary(),
        },
    }
