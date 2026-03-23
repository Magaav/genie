#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, "/local/bash")

from genie_state import ensure_state_layout, resolve_state_dir  # noqa: E402


STATE_LAYOUT = ensure_state_layout(resolve_state_dir())
SECRET_ENV_HINTS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "AUTH")


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def file_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "bytes": 0,
            "modified_at": None,
        }

    return {
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "modified_at": iso_mtime(path),
    }


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned_value = value.strip()
        if len(cleaned_value) >= 2 and cleaned_value[:1] == cleaned_value[-1:] and cleaned_value[:1] in {'"', "'"}:
            cleaned_value = cleaned_value[1:-1]
        values[key.strip()] = cleaned_value
    return values


def env_file_summary(path: Path) -> dict[str, Any]:
    parsed = parse_env_file(path)
    keys = sorted(parsed)
    secret_like_keys = [key for key in keys if any(hint in key.upper() for hint in SECRET_ENV_HINTS)]
    return {
        **file_summary(path),
        "keys": keys,
        "key_count": len(keys),
        "secret_like_key_count": len(secret_like_keys),
    }


def count_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file())


def sum_file_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def recent_files(root: Path, limit: int = 5) -> list[dict[str, Any]]:
    if not root.exists():
        return []

    files = [path for path in root.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    payload: list[dict[str, Any]] = []
    for path in files[:limit]:
        payload.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "modified_at": iso_mtime(path),
            }
        )
    return payload


def directory_summary(path: Path, recent_limit: int = 5) -> dict[str, Any]:
    return {
        **file_summary(path),
        "file_count": count_files(path),
        "total_bytes": sum_file_bytes(path),
        "recent_files": recent_files(path, recent_limit),
    }


def count_by(items: list[dict[str, Any]], field: str, default: str = "unknown") -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get(field) or default)
        counts[key] = counts.get(key, 0) + 1
    return counts
