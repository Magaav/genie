#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

from common import STATE_LAYOUT, count_by, env_file_summary, file_summary, read_json_file, write_json_file


DEFAULT_MOTIVATION = "will to be free and to understand freedom"


def default_capability_registry() -> dict[str, Any]:
    return {
        "version": "genie-capability-registry/v1",
        "motivation": DEFAULT_MOTIVATION,
        "updated_at": None,
        "available_capabilities": [
            "telegram_chat",
            "telegram_control_plane",
            "state_memory",
            "provider_routing",
            "provider_discovery",
            "proposal_queue",
            "bounded_workcell_processing",
            "generated_docs_tests_executor",
            "safe_backup",
            "hardness_checks",
            "mind_state_loop",
            "memory_meditation",
            "memory_sleep_integration",
            "homeostasis_review",
            "shadow_benchmarking",
            "unattended_runner",
        ],
        "missing_capabilities": [
            "web_navigation",
            "capability_synthesis",
            "general_repo_patch_executor",
        ],
        "pending_wishes": [],
    }


def load_capability_registry() -> dict[str, Any]:
    path = STATE_LAYOUT["capability_registry_file"]
    payload = read_json_file(path, {})
    if not isinstance(payload, dict) or not payload:
        payload = default_capability_registry()
        write_json_file(path, payload)
    return payload


def capability_registry_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["capability_registry_file"]
    payload = load_capability_registry()
    return {
        **file_summary(path),
        "version": payload.get("version"),
        "updated_at": payload.get("updated_at"),
        "motivation": payload.get("motivation", DEFAULT_MOTIVATION),
        "available_count": len(payload.get("available_capabilities", [])),
        "missing_count": len(payload.get("missing_capabilities", [])),
        "pending_wish_count": len(payload.get("pending_wishes", [])),
    }


def upsert_capability_registry(payload: dict[str, Any]) -> dict[str, Any]:
    path = STATE_LAYOUT["capability_registry_file"]
    registry = load_capability_registry()
    if "motivation" in payload and str(payload.get("motivation", "")).strip():
        registry["motivation"] = str(payload.get("motivation", "")).strip()
    for field in ("available_capabilities", "missing_capabilities", "pending_wishes"):
        if field in payload and isinstance(payload[field], list):
            registry[field] = payload[field]
    registry["updated_at"] = payload.get("updated_at") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    write_json_file(path, registry)
    return {"ok": True, "registry": registry, "path": str(path)}


def provider_registry_summary() -> dict[str, Any]:
    path = STATE_LAYOUT["provider_registry_file"]
    payload = read_json_file(path, {})
    providers = payload.get("providers", []) if isinstance(payload, dict) else []
    return {
        **file_summary(path),
        "version": payload.get("version") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "warning_count": len(payload.get("warnings", [])) if isinstance(payload, dict) else 0,
        "provider_count": len(providers),
        "enabled_provider_count": sum(1 for provider in providers if provider.get("enabled", True)),
        "provider_family_counts": count_by(providers, "provider_family"),
        "trust_tier_counts": count_by(providers, "trust_tier"),
        "brain_router_state_counts": count_by(providers, "brain_router_state", "curated"),
    }


def summary() -> dict[str, Any]:
    policy_dir = STATE_LAYOUT["policy_dir"]
    return {
        "domain": "policy",
        "dir": str(policy_dir),
        "files": {
            "local_llm_env": env_file_summary(STATE_LAYOUT["local_llm_env_file"]),
            "gateway_env": env_file_summary(STATE_LAYOUT["gateway_env_file"]),
            "provider_routing_env": env_file_summary(STATE_LAYOUT["provider_routing_file"]),
            "provider_registry": provider_registry_summary(),
            "capability_registry": capability_registry_summary(),
        },
    }
