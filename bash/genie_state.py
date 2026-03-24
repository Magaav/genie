#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_STATE_DIR = Path("/local/state/genie")
LEGACY_STATE_DIRS = (
    Path("/local/state/freewiller"),
    Path("/var/lib/freewiller"),
    Path("/var/lib/openclaw-local-llm"),
)


def resolve_state_dir() -> Path:
    explicit = os.environ.get("LOCAL_LLM_DIR", "").strip()
    if explicit:
        return Path(explicit)
    if DEFAULT_STATE_DIR.exists():
        return DEFAULT_STATE_DIR
    for candidate in LEGACY_STATE_DIRS:
        if candidate.exists():
            return candidate
    return DEFAULT_STATE_DIR


def build_layout(state_dir: Path | None = None) -> dict[str, Path]:
    root = Path(state_dir or resolve_state_dir())
    memory_dir = root / "memory"
    policy_dir = root / "policy"
    gateway_dir = root / "gateway"
    telemetry_dir = root / "telemetry"
    runtime_dir = root / "runtime"
    return {
        "state_dir": root,
        "memory_dir": memory_dir,
        "memory_db_file": memory_dir / "entries.jsonl",
        "memory_sqlite_file": memory_dir / "memory.sqlite3",
        "memory_journal_file": memory_dir / "journal.jsonl",
        "memory_projections_dir": memory_dir / "projections",
        "memory_daily_dir": memory_dir / "projections" / "memory",
        "policy_dir": policy_dir,
        "local_llm_env_file": policy_dir / "local-llm.env",
        "gateway_env_file": policy_dir / "genie-gateway.env",
        "provider_routing_file": policy_dir / "provider-routing.env",
        "provider_registry_file": policy_dir / "provider-registry.json",
        "gateway_dir": gateway_dir,
        "telemetry_dir": telemetry_dir,
        "runtime_dir": runtime_dir,
        "runtime_packages_dir": runtime_dir / "packages",
        "runtime_responses_dir": runtime_dir / "responses",
        "runtime_bridge_dir": runtime_dir / "bridge",
        "runtime_frontier_dir": runtime_dir / "frontier",
        "runtime_review_queue_file": runtime_dir / "review-queue.jsonl",
        "runtime_control_log_file": runtime_dir / "control-log.jsonl",
    }


def _unique_target(path: Path) -> Path:
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}.migrated-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _files_match(left: Path, right: Path) -> bool:
    try:
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def _merge_move(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.resolve() == destination.resolve():
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    if not destination.exists():
        source.rename(destination)
        return

    if source.is_dir() and destination.is_dir():
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            _merge_move(child, destination / child.name)
        try:
            source.rmdir()
        except OSError:
            pass
        return

    if source.is_file() and destination.is_file():
        if _files_match(source, destination):
            source.unlink()
            return
        source.rename(_unique_target(destination))
        return

    if source.is_dir() and destination.is_file():
        _merge_move(source, destination.parent / source.name)
        return

    if source.is_file() and destination.is_dir():
        _merge_move(source, destination / source.name)


def ensure_state_layout(state_dir: Path | None = None) -> dict[str, Path]:
    layout = build_layout(state_dir)
    state_dir = layout["state_dir"]

    for key in (
        "memory_dir",
        "policy_dir",
        "gateway_dir",
        "telemetry_dir",
        "runtime_dir",
        "runtime_packages_dir",
        "runtime_responses_dir",
        "runtime_bridge_dir",
        "runtime_frontier_dir",
        "memory_projections_dir",
        "memory_daily_dir",
    ):
        layout[key].mkdir(parents=True, exist_ok=True)

    migrations: list[tuple[Path, Path]] = [
        (state_dir / "projections", layout["memory_projections_dir"]),
        (state_dir / "packages", layout["runtime_packages_dir"]),
        (state_dir / "responses", layout["runtime_responses_dir"]),
        (state_dir / "bridge", layout["runtime_bridge_dir"]),
        (state_dir / "frontier", layout["runtime_frontier_dir"]),
        (layout["memory_dir"] / "responses", layout["runtime_responses_dir"]),
        (layout["memory_dir"] / "telemetry", layout["telemetry_dir"]),
        (state_dir / "local-llm.env", layout["local_llm_env_file"]),
        (state_dir / "genie-gateway.env", layout["gateway_env_file"]),
        (state_dir / "freewiller-gateway.env", layout["gateway_env_file"]),
        (state_dir / "openclaw-gateway.env", layout["gateway_env_file"]),
        (state_dir / "provider-routing.env", layout["provider_routing_file"]),
        (state_dir / "provider-router.env", layout["provider_routing_file"]),
        (state_dir / "provider-registry.json", layout["provider_registry_file"]),
        (state_dir / "providers.json", layout["provider_registry_file"]),
    ]

    for source, destination in migrations:
        if source.exists():
            _merge_move(source, destination)

    return layout


__all__ = [
    "build_layout",
    "ensure_state_layout",
    "resolve_state_dir",
]
