#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

from common import STATE_LAYOUT, count_by, env_file_summary, file_summary, read_json_file


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
        },
    }
