#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

import sys

sys.path.insert(0, "/local/bash")

import local_memory  # noqa: E402

from common import coerce_bool


def stats() -> dict[str, Any]:
    return local_memory.memory_stats()


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("text is required")
    return local_memory.ingest_event(
        channel=str(payload.get("channel", "http")),
        session_id=str(payload.get("session_id", "")),
        role=str(payload.get("role", "user")),
        user_id=str(payload.get("user_id", "")),
        source=str(payload.get("source", "http")),
        kind=str(payload.get("kind", "event")),
        text=text,
        tags=local_memory.normalize_tags(payload.get("tags", [])),
        metadata=local_memory.normalize_metadata(payload.get("metadata", {})),
        derive_memory=not coerce_bool(payload.get("skip_memory", False)),
        trust_class=str(payload.get("trust_class", "")),
        privacy_class=str(payload.get("privacy_class", "")),
        source_type=str(payload.get("source_type", "")),
        source_id=str(payload.get("source_id", "")),
        source_provider=str(payload.get("source_provider", "")),
        source_model=str(payload.get("source_model", "")),
        verification_status=str(payload.get("verification_status", "")),
        operator_confirmed=coerce_bool(payload.get("operator_confirmed", False)),
        policy_tags=local_memory.normalize_policy_tags(payload.get("policy_tags", [])),
    )


def search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    limit = int(payload.get("limit", 5))
    allowed_privacy = payload.get("allowed_privacy")
    return {"results": local_memory.search_memory_entries(query, limit, allowed_privacy)}


def context(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    limit = int(payload.get("limit", 5))
    allowed_privacy = payload.get("allowed_privacy")
    return {
        "context": local_memory.build_context(query, limit, allowed_privacy),
        "hits": local_memory.search_memory_entries(query, limit, allowed_privacy),
    }


def sync_projections() -> dict[str, Any]:
    local_memory.sync_projection_files()
    return {
        "status": "ok",
        "projection_memory_file": str(local_memory.PROJECTION_MEMORY_FILE),
    }


def try_sync_projections() -> None:
    local_memory.try_sync_projection_files()
