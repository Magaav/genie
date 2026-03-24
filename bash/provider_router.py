#!/usr/bin/env python3

import argparse
from collections import deque
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from genie_state import ensure_state_layout, resolve_state_dir


ROOT_DIR = Path("/local")
PRIMARY_ROUTER_ENV_BASENAME = "provider-routing.env"
LEGACY_ROUTER_ENV_BASENAME = "provider-router.env"
PRIMARY_GATEWAY_ENV_BASENAME = "genie-gateway.env"
SECONDARY_GATEWAY_ENV_BASENAME = "freewiller-gateway.env"
LEGACY_GATEWAY_ENV_BASENAME = "openclaw-gateway.env"
PRIMARY_REGISTRY_BASENAME = "provider-registry.json"
LEGACY_REGISTRY_BASENAME = "providers.json"
PRIMARY_ACCESS_ENV_FILE = ROOT_DIR / "docker" / "access.env"
PRIMARY_CONF_ENV_FILE = ROOT_DIR / "docker" / "conf.env"
LEGACY_DOCKER_ENV_FILE = ROOT_DIR / "docker" / ".env"
LEGACY_ROOT_ENV_FILE = ROOT_DIR / ".env"
REGISTRY_TEMPLATE_FILE = ROOT_DIR / "config" / "provider-registry.template.json"
BENCHMARKS_DIR = ROOT_DIR / "benchmarks" / "providers"
LOCAL_AGENT_PY = ROOT_DIR / "bash" / "local_agent.py"

TASK_CLASSES = {
    "architecture",
    "chat",
    "classify",
    "coding",
    "compact",
    "extract",
    "ops",
    "reflect",
    "research_public",
    "summarize",
}
PRIVACY_CLASSES = {"public", "internal", "private", "secret"}
TRUST_TIERS = {"frontier", "local", "trusted_external", "public_external"}
PROVIDER_KINDS = {"gateway", "openai_compatible"}
HEALTH_STATES = {"healthy", "degraded", "rate_limited", "auth_error", "disabled"}
BENCHMARK_PROFILES = {"summarize", "extract", "compact", "reflect", "research_public", "chat"}
PUBLIC_ELIGIBLE_TASKS = {"summarize", "extract", "classify", "compact", "reflect", "research_public"}
CHEAP_ELIGIBLE_TASKS = PUBLIC_ELIGIBLE_TASKS | {"chat"}
FRONTIER_ONLY_TASKS = {"architecture", "coding", "ops"}
FAST_LOOP_TASKS = {"chat", "classify", "extract", "summarize"}
SLOW_POWERFUL_TASKS = {"compact", "reflect", "research_public"}
TASK_PROFILE_MAP = {
    "summarize": "summarize",
    "extract": "extract",
    "compact": "compact",
    "reflect": "reflect",
    "research_public": "research_public",
    "chat": "chat",
}
TRUST_SCORE_MAP = {
    "frontier": 1.0,
    "local": 1.0,
    "trusted_external": 0.7,
    "public_external": 0.4,
}
DEFAULT_BENCHMARK_QUALITY = {
    "frontier": 0.92,
    "local": 0.65,
    "trusted_external": 0.62,
    "public_external": 0.52,
}
DEFAULT_COST_SCORE = {
    "frontier": 0.10,
    "local": 1.00,
    "trusted_external": 0.70,
    "public_external": 0.80,
}
DEFAULT_SUCCESS_RATE = {
    "frontier": 0.99,
    "local": 0.90,
    "trusted_external": 0.82,
    "public_external": 0.72,
}
COOLDOWN_SECONDS = {
    "rate_limited": 600,
    "degraded": 300,
}
SCORE_WEIGHTS = {
    "benchmark_quality": 0.45,
    "recent_success_rate": 0.20,
    "latency_score": 0.15,
    "cost_score": 0.10,
    "trust_score": 0.10,
}
SCORECARD_WINDOW = 400
DIRECT_CONFIDENCE_THRESHOLD = 0.62
FRONTIER_REVIEW_CONFIDENCE_THRESHOLD = 0.56
SMALL_GAP_THRESHOLD = 0.05
FRONTIER_REVIEW_TASKS = {"chat", "summarize", "extract", "compact", "reflect", "research_public"}
AUTO_DISCOVERY_PREFIXES = ("nvidia_auto_", "openrouter_auto_")
AUTO_DISCOVERY_SOURCES = {"nvidia:/v1/models", "openrouter:/models"}
NVIDIA_MODEL_CATALOG = [
    {
        "id": "nvidia_gpt_oss_120b",
        "label": "NVIDIA GPT OSS 120B",
        "model": "openai/gpt-oss-120b",
        "latency_tier": "normal",
        "strength_tier": "powerful",
        "interactive": True,
        "allowed_tasks": sorted(CHEAP_ELIGIBLE_TASKS),
        "max_output_tokens": 4096,
        "request_timeout_seconds": 90,
        "extra_body": {},
    },
    {
        "id": "nvidia_kimi_k2_instruct",
        "label": "NVIDIA Kimi K2 Instruct",
        "model": "moonshotai/kimi-k2-instruct",
        "latency_tier": "normal",
        "strength_tier": "strong",
        "interactive": True,
        "allowed_tasks": sorted(CHEAP_ELIGIBLE_TASKS),
        "max_output_tokens": 4096,
        "request_timeout_seconds": 90,
        "extra_body": {},
    },
    {
        "id": "nvidia_qwen3_next_80b_a3b_instruct",
        "label": "NVIDIA Qwen3 Next 80B A3B Instruct",
        "model": "qwen/qwen3-next-80b-a3b-instruct",
        "latency_tier": "normal",
        "strength_tier": "powerful",
        "interactive": True,
        "allowed_tasks": sorted(CHEAP_ELIGIBLE_TASKS),
        "max_output_tokens": 4096,
        "request_timeout_seconds": 120,
        "extra_body": {},
    },
    {
        "id": "nvidia_kimi_k2_5",
        "label": "NVIDIA Kimi K2.5",
        "model": "moonshotai/kimi-k2.5",
        "latency_tier": "slow",
        "strength_tier": "powerful",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 1024,
        "request_timeout_seconds": 240,
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    {
        "id": "nvidia_glm5",
        "label": "NVIDIA GLM5",
        "model": "z-ai/glm5",
        "latency_tier": "slow",
        "strength_tier": "powerful",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 16384,
        "request_timeout_seconds": 240,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}},
    },
    {
        "id": "nvidia_glm4_7",
        "label": "NVIDIA GLM4.7",
        "model": "z-ai/glm4.7",
        "latency_tier": "slow",
        "strength_tier": "powerful",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 16384,
        "request_timeout_seconds": 240,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}},
    },
    {
        "id": "nvidia_deepseek_v3_1",
        "label": "NVIDIA DeepSeek V3.1",
        "model": "deepseek-ai/deepseek-v3.1",
        "latency_tier": "slow",
        "strength_tier": "powerful",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 8192,
        "request_timeout_seconds": 240,
        "extra_body": {"chat_template_kwargs": {"thinking": True}},
    },
    {
        "id": "nvidia_qwen3_5_397b_a17b",
        "label": "NVIDIA Qwen3.5 397B A17B",
        "model": "qwen/qwen3.5-397b-a17b",
        "latency_tier": "slow",
        "strength_tier": "powerful",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 16384,
        "request_timeout_seconds": 240,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    },
    {
        "id": "nvidia_nemotron_3_nano_30b_a3b",
        "label": "NVIDIA Nemotron 3 Nano 30B A3B",
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "latency_tier": "slow",
        "strength_tier": "strong",
        "interactive": False,
        "allowed_tasks": sorted(SLOW_POWERFUL_TASKS),
        "max_output_tokens": 16384,
        "request_timeout_seconds": 240,
        "extra_body": {"reasoning_budget": 16384, "chat_template_kwargs": {"enable_thinking": True}},
    },
]

STATE_LAYOUT = ensure_state_layout(resolve_state_dir())
LOCAL_LLM_DIR = STATE_LAYOUT["state_dir"]
PRIMARY_ROUTER_ENV_FILE = STATE_LAYOUT["provider_routing_file"]
LEGACY_ROUTER_ENV_FILE = LOCAL_LLM_DIR / LEGACY_ROUTER_ENV_BASENAME
PRIMARY_GATEWAY_ENV_FILE = STATE_LAYOUT["gateway_env_file"]
SECONDARY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / SECONDARY_GATEWAY_ENV_BASENAME
LEGACY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / LEGACY_GATEWAY_ENV_BASENAME
PRIMARY_REGISTRY_FILE = STATE_LAYOUT["provider_registry_file"]
LEGACY_REGISTRY_FILE = LOCAL_LLM_DIR / LEGACY_REGISTRY_BASENAME
TELEMETRY_DIR = STATE_LAYOUT["telemetry_dir"]
DEFAULT_USAGE_LEDGER_FILE = TELEMETRY_DIR / "provider-usage.jsonl"
DEFAULT_HEALTH_FILE = TELEMETRY_DIR / "provider-health.json"
DEFAULT_BENCHMARKS_FILE = TELEMETRY_DIR / "provider-benchmarks.json"
DEFAULT_SCORECARDS_FILE = TELEMETRY_DIR / "provider-scorecards.json"
DEFAULT_DISCOVERY_FILE = TELEMETRY_DIR / "provider-discovery.json"
DISCOVERY_IMPORT_LIMIT = 24
BRAIN_ROUTER_STATES = {
    "curated",
    "discovered",
    "benchmark_pending",
    "eligible",
    "leader",
    "degraded",
    "retired",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso8601(value: str) -> datetime | None:
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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


def read_repo_env_keys() -> list[str]:
    keys: list[str] = []
    for env_file in (PRIMARY_ACCESS_ENV_FILE, PRIMARY_CONF_ENV_FILE, LEGACY_DOCKER_ENV_FILE, LEGACY_ROOT_ENV_FILE):
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key:
                keys.append(key)
    return keys


def load_raw_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (
        PRIMARY_ACCESS_ENV_FILE,
        PRIMARY_CONF_ENV_FILE,
        LEGACY_DOCKER_ENV_FILE,
        LEGACY_ROOT_ENV_FILE,
        PRIMARY_ROUTER_ENV_FILE,
        LEGACY_ROUTER_ENV_FILE,
        PRIMARY_GATEWAY_ENV_FILE,
        SECONDARY_GATEWAY_ENV_FILE,
        LEGACY_GATEWAY_ENV_FILE,
    ):
        values.update(parse_env_file(path))

    for key, value in os.environ.items():
        values[key] = value
    return values


def env_get(raw: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return value
    return default


def first_present_key(raw: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return key
    return ""


def env_bool(raw: dict[str, str], key: str, default: bool) -> bool:
    value = raw.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(raw: dict[str, str], key: str, default: int) -> int:
    value = raw.get(key)
    if value is None or value == "":
        return default
    return int(value)


def env_float(raw: dict[str, str], key: str) -> float | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    return float(value)


def sanitize_provider_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower())


def normalize_task_class(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in TASK_CLASSES:
        return candidate
    return ""


def normalize_privacy_class(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in PRIVACY_CLASSES:
        return candidate
    return ""


def normalize_complexity_class(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in {"low", "medium", "high"}:
        return candidate
    return ""


def normalize_trust_tier(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in TRUST_TIERS:
        return candidate
    return ""


def normalize_kind(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in PROVIDER_KINDS:
        return candidate
    return ""


def normalize_brain_router_state(value: str) -> str:
    candidate = value.strip().lower()
    if candidate in BRAIN_ROUTER_STATES:
        return candidate
    return ""


def normalize_task_list(values: Any, default: list[str]) -> list[str]:
    if isinstance(values, list):
        normalized = [normalize_task_class(str(item)) for item in values]
        filtered = [item for item in normalized if item]
        return filtered or default
    return default


def normalize_privacy_list(values: Any, default: list[str]) -> list[str]:
    if isinstance(values, list):
        normalized = [normalize_privacy_class(str(item)) for item in values]
        filtered = [item for item in normalized if item]
        return filtered or default
    return default


def normalize_usage_ledger_file(path_value: str) -> str:
    candidate = (path_value or "").strip()
    if not candidate:
        return str(DEFAULT_USAGE_LEDGER_FILE)
    if candidate == "/local/state/freewiller/telemetry/provider-usage.jsonl" and str(LOCAL_LLM_DIR) == "/local/state/genie":
        return str(DEFAULT_USAGE_LEDGER_FILE)
    return candidate


def normalize_profile_list(values: Any, allowed_tasks: list[str]) -> list[str]:
    if isinstance(values, list):
        filtered = [str(item).strip().lower() for item in values if str(item).strip().lower() in BENCHMARK_PROFILES]
        if filtered:
            return filtered
    profiles = [TASK_PROFILE_MAP[task] for task in allowed_tasks if task in TASK_PROFILE_MAP]
    return sorted(set(profiles))


def infer_task_class(task: str) -> str:
    text = " ".join(task.lower().split())
    if any(token in text for token in ("summarize", "summary", "compress", "tl;dr")):
        return "summarize"
    if any(token in text for token in ("extract", "facts", "todos", "constraints", "entities", "keywords")):
        return "extract"
    if any(token in text for token in ("classify", "label", "route", "tag")):
        return "classify"
    if any(token in text for token in ("compact", "distill", "merge memory", "rewrite memory", "curate memory")):
        return "compact"
    if any(token in text for token in ("reflect", "retrospective", "lesson", "postmortem")):
        return "reflect"
    if any(token in text for token in ("research", "look up", "find sources", "collect sources", "public docs")):
        return "research_public"
    if any(token in text for token in ("docker", "service", "systemctl", "vm", "server", "ssh", "cron", "deploy", "restart")):
        return "ops"
    if any(token in text for token in ("code", "implement", "patch", "debug", "refactor", "test", "script", "function")):
        return "coding"
    if any(token in text for token in ("architecture", "design", "roadmap", "strategy", "memory spec", "security")):
        return "architecture"
    return "chat"


def infer_privacy_class(task: str, default_privacy: str) -> str:
    text = " ".join(task.lower().split())
    if any(token in text for token in ("api key", "token", "secret", "password", "ssh key", "private key", "credential")):
        return "secret"
    if any(token in text for token in ("wife", "family", "marriage", "relationship", "personal", "private", "telegram dm")):
        return "private"
    if any(token in text for token in ("public repo", "open source", "public docs", "website", "blog post", "readme")):
        return "public"
    return default_privacy


def detect_repo_env_warnings() -> list[str]:
    warnings: list[str] = []
    repo_keys = read_repo_env_keys()
    if "NVIDEA_KIMI_K2.5_API_KEY" in repo_keys:
        warnings.append(
            "Unsupported .env key NVIDEA_KIMI_K2.5_API_KEY detected. Rename it to NVIDIA_API_KEY."
        )

    for key in repo_keys:
        if "." in key:
            warnings.append(f"Unsupported dotted .env key ignored: {key}")
    return sorted(set(warnings))


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def default_registry_entry_frontier(raw: dict[str, str]) -> dict[str, Any]:
    return {
        "id": "frontier_gateway",
        "label": "Frontier Gateway",
        "enabled": True,
        "provider_family": "frontier",
        "kind": "gateway",
        "api_key_env": "",
        "api_base_url": env_get(raw, "FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL"),
        "model": env_get(raw, "FREEWILLER_MODEL", "OPENCLAW_MODEL", default="genie:main"),
        "api_mode": env_get(raw, "FREEWILLER_GATEWAY_API", "OPENCLAW_GATEWAY_API", default="auto"),
        "extra_body": {},
        "trust_tier": "frontier",
        "allowed_privacy": ["public", "internal", "private", "secret"],
        "allowed_tasks": sorted(TASK_CLASSES),
        "max_output_tokens": env_int(raw, "FREEWILLER_MAX_OUTPUT_TOKENS", env_int(raw, "OPENCLAW_MAX_OUTPUT_TOKENS", 2048)),
        "request_timeout_seconds": env_int(raw, "FREEWILLER_FRONTIER_REQUEST_TIMEOUT_SECONDS", env_int(raw, "FRONTIER_REQUEST_TIMEOUT_SECONDS", 90)),
        "cost_input_per_million": env_float(raw, "FREEWILLER_FRONTIER_INPUT_COST_PER_MILLION"),
        "cost_output_per_million": env_float(raw, "FREEWILLER_FRONTIER_OUTPUT_COST_PER_MILLION"),
        "benchmark_profiles": sorted(BENCHMARK_PROFILES),
        "brain_router_state": "curated",
    }


def default_registry_entries_nvidia(raw: dict[str, str]) -> list[dict[str, Any]]:
    api_key_env = first_present_key(raw, "NVIDIA_API_KEY", "FREEWILLER_NVIDIA_API_KEY", "NGC_API_KEY", "NVIDIA_KIMI_K25_API_KEY")
    if not api_key_env:
        return []

    api_base_url = env_get(raw, "FREEWILLER_NVIDIA_API_BASE_URL", "NVIDIA_API_BASE_URL", default="https://integrate.api.nvidia.com/v1")
    api_mode = env_get(raw, "FREEWILLER_NVIDIA_API_MODE", "NVIDIA_API_MODE", default="chat")
    entries: list[dict[str, Any]] = []

    for spec in NVIDIA_MODEL_CATALOG:
        entries.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "enabled": True,
                "provider_family": "nvidia",
                "kind": "openai_compatible",
                "api_key_env": api_key_env,
                "api_base_url": api_base_url,
                "model": spec["model"],
                "api_mode": api_mode,
                "extra_body": spec.get("extra_body", {}),
                "trust_tier": "trusted_external",
                "latency_tier": spec.get("latency_tier", "normal"),
                "strength_tier": spec.get("strength_tier", "strong"),
                "interactive": bool(spec.get("interactive", True)),
                "allowed_privacy": ["public", "internal"],
                "allowed_tasks": list(spec["allowed_tasks"]),
                "max_output_tokens": int(spec["max_output_tokens"]),
                "request_timeout_seconds": int(spec["request_timeout_seconds"]),
                "cost_input_per_million": env_float(raw, f"{spec['id'].upper()}_INPUT_COST_PER_MILLION"),
                "cost_output_per_million": env_float(raw, f"{spec['id'].upper()}_OUTPUT_COST_PER_MILLION"),
                "benchmark_profiles": sorted(BENCHMARK_PROFILES),
                "brain_router_state": "curated",
            }
        )

    return entries


def default_registry_entry_openrouter(raw: dict[str, str]) -> dict[str, Any] | None:
    api_key_env = first_present_key(raw, "FREEWILLER_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    if not api_key_env:
        return None

    free_only = env_bool(raw, "FREEWILLER_OPENROUTER_FREE_ONLY", env_bool(raw, "OPENROUTER_FREE_ONLY", True))
    return {
        "id": "openrouter_auto",
        "label": "OpenRouter Free Router" if free_only else "OpenRouter Auto",
        "enabled": True,
        "provider_family": "openrouter",
        "kind": "openai_compatible",
        "api_key_env": api_key_env,
        "api_base_url": env_get(raw, "FREEWILLER_OPENROUTER_API_BASE_URL", "OPENROUTER_API_BASE_URL", default="https://openrouter.ai/api/v1"),
        "model": env_get(
            raw,
            "FREEWILLER_OPENROUTER_MODEL",
            "OPENROUTER_MODEL",
            default="openrouter/free" if free_only else "openrouter/auto",
        ),
        "api_mode": env_get(raw, "FREEWILLER_OPENROUTER_API_MODE", "OPENROUTER_API_MODE", default="chat"),
        "extra_body": {},
        "trust_tier": "trusted_external",
        "allowed_privacy": ["public", "internal"],
        "allowed_tasks": sorted(CHEAP_ELIGIBLE_TASKS),
        "max_output_tokens": env_int(raw, "FREEWILLER_OPENROUTER_MAX_OUTPUT_TOKENS", env_int(raw, "OPENROUTER_MAX_OUTPUT_TOKENS", 1024)),
        "request_timeout_seconds": env_int(raw, "FREEWILLER_OPENROUTER_REQUEST_TIMEOUT_SECONDS", env_int(raw, "OPENROUTER_REQUEST_TIMEOUT_SECONDS", 90)),
        "cost_input_per_million": env_float(raw, "FREEWILLER_OPENROUTER_INPUT_COST_PER_MILLION"),
        "cost_output_per_million": env_float(raw, "FREEWILLER_OPENROUTER_OUTPUT_COST_PER_MILLION"),
        "benchmark_profiles": sorted(BENCHMARK_PROFILES),
        "brain_router_state": "curated",
    }


def default_registry_entry_legacy(raw: dict[str, str], *, public_only: bool) -> dict[str, Any] | None:
    prefix = "FREEWILLER_PUBLIC" if public_only else "FREEWILLER_CHEAP"
    api_base_url = env_get(raw, f"{prefix}_API_BASE_URL")
    api_key = env_get(raw, f"{prefix}_API_KEY")
    model = env_get(raw, f"{prefix}_MODEL")
    if not api_base_url or not api_key or not model:
        return None

    return {
        "id": "legacy_public" if public_only else "legacy_cheap",
        "label": "Legacy Public Lane" if public_only else "Legacy Cheap Lane",
        "enabled": True,
        "provider_family": "legacy",
        "kind": "openai_compatible",
        "api_key_env": f"{prefix}_API_KEY",
        "api_base_url": api_base_url,
        "model": model,
        "api_mode": env_get(raw, f"{prefix}_API_MODE", default="chat"),
        "extra_body": {},
        "trust_tier": "public_external" if public_only else "trusted_external",
        "allowed_privacy": ["public"] if public_only else ["public", "internal"],
        "allowed_tasks": sorted(PUBLIC_ELIGIBLE_TASKS if public_only else CHEAP_ELIGIBLE_TASKS),
        "max_output_tokens": env_int(raw, f"{prefix}_MAX_OUTPUT_TOKENS", 1024),
        "request_timeout_seconds": env_int(raw, f"{prefix}_REQUEST_TIMEOUT_SECONDS", 90),
        "cost_input_per_million": env_float(raw, f"{prefix}_INPUT_COST_PER_MILLION"),
        "cost_output_per_million": env_float(raw, f"{prefix}_OUTPUT_COST_PER_MILLION"),
        "benchmark_profiles": sorted(BENCHMARK_PROFILES),
        "brain_router_state": "curated",
    }


def nvidia_curated_model_ids() -> set[str]:
    return {str(item.get("model", "")).strip() for item in NVIDIA_MODEL_CATALOG}


def openrouter_curated_model_ids() -> set[str]:
    return {"openrouter/auto"}


def is_discoverable_nvidia_text_model(model_id: str) -> bool:
    value = model_id.strip().lower()
    if not value:
        return False
    blocked_tokens = {
        "embed",
        "bge-",
        "vision",
        "vlm",
        "video",
        "image",
        "paligemma",
        "deplot",
        "kosmos",
        "fuyu",
        "guard",
        "guardian",
        "shieldgemma",
        "cosmos",
        "rerank",
        "nv-embed",
    }
    if any(token in value for token in blocked_tokens):
        return False
    keep_tokens = {
        "instruct",
        "chat",
        "reason",
        "coder",
        "code",
        "oss",
        "llama",
        "qwen",
        "deepseek",
        "kimi",
        "glm",
        "gemma",
        "granite",
        "mistral",
        "codestral",
        "devstral",
        "phi",
        "jamba",
        "dbrx",
        "nemotron",
        "seed-oss",
        "minimax",
        "yi-large",
        "baichuan",
        "starcoder",
    }
    return any(token in value for token in keep_tokens)


def parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_discoverable_openrouter_text_model(item: dict[str, Any]) -> bool:
    model_id = str(item.get("model") or item.get("id", "")).strip().lower()
    if not model_id:
        return False

    blocked_tokens = {
        "embed",
        "rerank",
        "omni",
        "vision",
        "vlm",
        "image",
        "audio",
        "video",
        "speech",
        "whisper",
        "tts",
        "transcribe",
        "transcription",
        "moderat",
        "guard",
    }
    if any(token in model_id for token in blocked_tokens):
        return False

    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        input_modalities = architecture.get("input_modalities")
        output_modalities = architecture.get("output_modalities")
        modality = str(architecture.get("modality", "")).strip().lower()
        if isinstance(input_modalities, list) and any(str(modality_name).strip().lower() != "text" for modality_name in input_modalities):
            return False
        if isinstance(output_modalities, list) and any(str(modality_name).strip().lower() != "text" for modality_name in output_modalities):
            return False
        if any(token in modality for token in ("image", "audio", "video")):
            return False

    keep_tokens = {
        "gpt",
        "llama",
        "qwen",
        "deepseek",
        "kimi",
        "glm",
        "gemma",
        "mistral",
        "codestral",
        "devstral",
        "ministral",
        "claude",
        "opus",
        "sonnet",
        "haiku",
        "grok",
        "gemini",
        "command",
        "jamba",
        "yi-",
        "granite",
        "starcoder",
        "coder",
        "code",
        "reason",
        "chat",
        "instruct",
        "mini",
        "nano",
    }
    return any(token in model_id for token in keep_tokens)


def infer_discovered_nvidia_profile(model_id: str) -> dict[str, Any]:
    value = model_id.lower()
    interactive = True
    latency_tier = "normal"
    strength_tier = "strong"
    allowed_tasks = sorted(CHEAP_ELIGIBLE_TASKS)
    max_output_tokens = 4096
    request_timeout_seconds = 120

    if any(token in value for token in ("405b", "397b", "355b", "123b", "120b", "70b", "90b", "405", "reason")):
        latency_tier = "slow"
        interactive = False
        strength_tier = "powerful"
        allowed_tasks = sorted(SLOW_POWERFUL_TASKS)
        max_output_tokens = 8192
        request_timeout_seconds = 240
    elif any(token in value for token in ("27b", "34b", "32b", "22b", "17b", "16e", "128e", "14b")):
        strength_tier = "powerful"
    elif any(token in value for token in ("3b", "7b", "8b", "mini", "nano")):
        strength_tier = "standard"

    return {
        "interactive": interactive,
        "latency_tier": latency_tier,
        "strength_tier": strength_tier,
        "allowed_tasks": allowed_tasks,
        "max_output_tokens": max_output_tokens,
        "request_timeout_seconds": request_timeout_seconds,
    }


def infer_discovered_openrouter_profile(item: dict[str, Any]) -> dict[str, Any]:
    model_id = str(item.get("model") or item.get("id", "")).lower()
    context_length = int(item.get("context_length") or 0)
    prompt_cost_per_million = parse_optional_float(item.get("prompt_cost_per_million"))
    completion_cost_per_million = parse_optional_float(item.get("completion_cost_per_million"))

    interactive = True
    latency_tier = "normal"
    strength_tier = "strong"
    allowed_tasks = sorted(CHEAP_ELIGIBLE_TASKS)
    max_output_tokens = 4096
    request_timeout_seconds = 120

    if any(token in model_id for token in ("opus", "sonnet", "grok-4", "gpt-5", "reason", "405b", "397b", "120b", "123b", "70b", "90b")):
        interactive = False
        latency_tier = "slow"
        strength_tier = "powerful"
        allowed_tasks = sorted(SLOW_POWERFUL_TASKS)
        max_output_tokens = 8192
        request_timeout_seconds = 240
    elif any(token in model_id for token in ("mini", "nano", "3b", "7b", "8b")):
        strength_tier = "standard"
    elif any(token in model_id for token in ("32b", "34b", "27b", "22b", "17b", "14b")):
        strength_tier = "powerful"

    if context_length >= 500_000 and latency_tier != "slow":
        latency_tier = "slow"
        interactive = False
        allowed_tasks = sorted(SLOW_POWERFUL_TASKS)
        max_output_tokens = max(max_output_tokens, 8192)
        request_timeout_seconds = max(request_timeout_seconds, 180)

    free_candidate = bool(item.get("free_candidate"))
    if free_candidate and interactive:
        request_timeout_seconds = min(request_timeout_seconds, 90)

    return {
        "interactive": interactive,
        "latency_tier": latency_tier,
        "strength_tier": strength_tier,
        "allowed_tasks": allowed_tasks,
        "max_output_tokens": max_output_tokens,
        "request_timeout_seconds": request_timeout_seconds,
        "cost_input_per_million": prompt_cost_per_million,
        "cost_output_per_million": completion_cost_per_million,
    }


def discovery_registry_entries_nvidia(raw: dict[str, str], discovery_store: dict[str, Any]) -> list[dict[str, Any]]:
    api_key_env = first_present_key(raw, "NVIDIA_API_KEY", "FREEWILLER_NVIDIA_API_KEY", "NGC_API_KEY", "NVIDIA_KIMI_K25_API_KEY")
    if not api_key_env:
        return []

    provider_store = discovery_store.get("providers", {}).get("nvidia", {})
    candidates = provider_store.get("candidate_entries", [])
    if not isinstance(candidates, list):
        return []

    api_base_url = env_get(raw, "FREEWILLER_NVIDIA_API_BASE_URL", "NVIDIA_API_BASE_URL", default="https://integrate.api.nvidia.com/v1")
    api_mode = env_get(raw, "FREEWILLER_NVIDIA_API_MODE", "NVIDIA_API_MODE", default="chat")
    entries: list[dict[str, Any]] = []
    curated_model_ids = nvidia_curated_model_ids()

    for candidate in candidates[:DISCOVERY_IMPORT_LIMIT]:
        if not isinstance(candidate, dict):
            continue
        model = str(candidate.get("model", "")).strip()
        if not model or model in curated_model_ids:
            continue
        profile = infer_discovered_nvidia_profile(model)
        entries.append(
            {
                "id": sanitize_provider_name(f"nvidia_auto_{model}"),
                "label": f"NVIDIA Auto {model}",
                "enabled": False,
                "provider_family": "nvidia",
                "kind": "openai_compatible",
                "api_key_env": api_key_env,
                "api_base_url": api_base_url,
                "model": model,
                "api_mode": api_mode,
                "extra_body": {},
                "trust_tier": "trusted_external",
                "latency_tier": profile["latency_tier"],
                "strength_tier": profile["strength_tier"],
                "interactive": profile["interactive"],
                "allowed_privacy": ["public", "internal"],
                "allowed_tasks": profile["allowed_tasks"],
                "max_output_tokens": profile["max_output_tokens"],
                "request_timeout_seconds": profile["request_timeout_seconds"],
                "cost_input_per_million": None,
                "cost_output_per_million": None,
                "benchmark_profiles": sorted(BENCHMARK_PROFILES),
                "brain_router_state": "benchmark_pending",
                "discovered_at": str(candidate.get("discovered_at", provider_store.get("updated_at", ""))),
                "discovery_source": "nvidia:/v1/models",
                "source_owned_by": str(candidate.get("owned_by", "")),
            }
        )
    return entries


def discovery_registry_entries_openrouter(raw: dict[str, str], discovery_store: dict[str, Any]) -> list[dict[str, Any]]:
    api_key_env = first_present_key(raw, "FREEWILLER_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    if not api_key_env:
        return []

    provider_store = discovery_store.get("providers", {}).get("openrouter", {})
    candidates = provider_store.get("candidate_entries", [])
    if not isinstance(candidates, list):
        return []

    api_base_url = env_get(raw, "FREEWILLER_OPENROUTER_API_BASE_URL", "OPENROUTER_API_BASE_URL", default="https://openrouter.ai/api/v1")
    api_mode = env_get(raw, "FREEWILLER_OPENROUTER_API_MODE", "OPENROUTER_API_MODE", default="chat")
    free_only = env_bool(raw, "FREEWILLER_OPENROUTER_FREE_ONLY", env_bool(raw, "OPENROUTER_FREE_ONLY", True))
    entries: list[dict[str, Any]] = []
    curated_model_ids = openrouter_curated_model_ids()

    sorted_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, dict) and (candidate.get("free_candidate") if free_only else True)
        ),
        key=lambda candidate: (
            0 if candidate.get("free_candidate") else 1,
            parse_optional_float(candidate.get("prompt_cost_per_million")) or 999999.0,
            parse_optional_float(candidate.get("completion_cost_per_million")) or 999999.0,
            str(candidate.get("model", "")),
        ),
    )

    for candidate in sorted_candidates[:DISCOVERY_IMPORT_LIMIT]:
        model = str(candidate.get("model", "")).strip()
        if not model or model in curated_model_ids:
            continue
        profile = infer_discovered_openrouter_profile(candidate)
        label_suffix = " (Free)" if candidate.get("free_candidate") else ""
        entries.append(
            {
                "id": sanitize_provider_name(f"openrouter_auto_{model}"),
                "label": f"OpenRouter Auto {candidate.get('name') or model}{label_suffix}",
                "enabled": False,
                "provider_family": "openrouter",
                "kind": "openai_compatible",
                "api_key_env": api_key_env,
                "api_base_url": api_base_url,
                "model": model,
                "api_mode": api_mode,
                "extra_body": {},
                "trust_tier": "trusted_external",
                "latency_tier": profile["latency_tier"],
                "strength_tier": profile["strength_tier"],
                "interactive": profile["interactive"],
                "allowed_privacy": ["public", "internal"],
                "allowed_tasks": profile["allowed_tasks"],
                "max_output_tokens": profile["max_output_tokens"],
                "request_timeout_seconds": profile["request_timeout_seconds"],
                "cost_input_per_million": profile["cost_input_per_million"],
                "cost_output_per_million": profile["cost_output_per_million"],
                "benchmark_profiles": sorted(BENCHMARK_PROFILES),
                "brain_router_state": "benchmark_pending",
                "discovered_at": str(candidate.get("discovered_at", provider_store.get("updated_at", ""))),
                "discovery_source": "openrouter:/models",
                "source_owned_by": str(candidate.get("owned_by", "")),
            }
        )
    return entries


def default_registry_entries(raw: dict[str, str]) -> list[dict[str, Any]]:
    discovery_store = load_discovery_store()
    entries: list[dict[str, Any]] = [default_registry_entry_frontier(raw)]
    nvidia_entries = default_registry_entries_nvidia(raw)
    discovered_nvidia_entries = discovery_registry_entries_nvidia(raw, discovery_store)
    discovered_openrouter_entries = discovery_registry_entries_openrouter(raw, discovery_store)
    openrouter_entry = default_registry_entry_openrouter(raw)
    legacy_cheap_entry = default_registry_entry_legacy(raw, public_only=False)
    legacy_public_entry = default_registry_entry_legacy(raw, public_only=True)

    if nvidia_entries:
        legacy_cheap_entry = None
    if openrouter_entry:
        legacy_public_entry = None

    entries.extend(nvidia_entries)
    entries.extend(discovered_nvidia_entries)
    entries.extend(discovered_openrouter_entries)
    for candidate in (openrouter_entry, legacy_cheap_entry, legacy_public_entry):
        if candidate:
            entries.append(candidate)
    return entries


def normalize_provider_entry(raw_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(raw_entry)
    entry_id = sanitize_provider_name(str(entry.get("id", "")))
    provider_family = sanitize_provider_name(str(entry.get("provider_family", "generic"))) or "generic"
    kind = normalize_kind(str(entry.get("kind", "openai_compatible"))) or "openai_compatible"
    trust_tier = normalize_trust_tier(str(entry.get("trust_tier", "trusted_external"))) or "trusted_external"
    enabled = bool(entry.get("enabled", True))
    allowed_privacy = normalize_privacy_list(entry.get("allowed_privacy"), ["public", "internal"])
    allowed_tasks = normalize_task_list(entry.get("allowed_tasks"), sorted(CHEAP_ELIGIBLE_TASKS))
    max_output_tokens = int(entry.get("max_output_tokens", 1024))
    request_timeout_seconds = int(entry.get("request_timeout_seconds", 90))
    interactive = bool(entry.get("interactive", True))
    api_mode = str(entry.get("api_mode", "chat")).strip().lower() or "chat"
    brain_router_state = normalize_brain_router_state(str(entry.get("brain_router_state", "eligible"))) or "eligible"
    extra_body = entry.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}

    return {
        "id": entry_id,
        "label": str(entry.get("label", entry_id.replace("_", " ").title())),
        "enabled": enabled,
        "provider_family": provider_family,
        "kind": kind,
        "api_key_env": str(entry.get("api_key_env", "")).strip(),
        "api_base_url": str(entry.get("api_base_url", "")).strip(),
        "model": str(entry.get("model", "")).strip(),
        "api_mode": api_mode,
        "extra_body": extra_body,
        "trust_tier": trust_tier,
        "latency_tier": str(entry.get("latency_tier", "normal")).strip() or "normal",
        "strength_tier": str(entry.get("strength_tier", "standard")).strip() or "standard",
        "interactive": interactive,
        "brain_router_state": brain_router_state,
        "discovered_at": str(entry.get("discovered_at", "")).strip(),
        "discovery_source": str(entry.get("discovery_source", "")).strip(),
        "source_owned_by": str(entry.get("source_owned_by", "")).strip(),
        "allowed_privacy": allowed_privacy,
        "allowed_tasks": allowed_tasks,
        "max_output_tokens": max_output_tokens,
        "request_timeout_seconds": request_timeout_seconds,
        "cost_input_per_million": entry.get("cost_input_per_million"),
        "cost_output_per_million": entry.get("cost_output_per_million"),
        "benchmark_profiles": normalize_profile_list(entry.get("benchmark_profiles"), allowed_tasks),
    }


def merge_registry_entries(existing_entries: list[dict[str, Any]], auto_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    auto_index = {entry["id"]: normalize_provider_entry(entry) for entry in auto_entries}
    auto_managed_ids = set(auto_index.keys())

    for entry in auto_entries:
        normalized = normalize_provider_entry(entry)
        merged[normalized["id"]] = normalized

    for raw_entry in existing_entries:
        normalized = normalize_provider_entry(raw_entry)
        auto_entry = auto_index.get(normalized["id"])
        if auto_entry:
            combined = dict(auto_entry)
            if "enabled" in normalized:
                combined["enabled"] = normalized["enabled"]
            merged[normalized["id"]] = normalize_provider_entry(combined)
        else:
            if normalized.get("discovery_source") in AUTO_DISCOVERY_SOURCES or normalized["id"].startswith(AUTO_DISCOVERY_PREFIXES):
                continue
            if normalized["id"] in auto_managed_ids:
                continue
            merged[normalized["id"]] = normalized

    return [merged[key] for key in sorted(merged.keys())]


def load_registry_payload() -> dict[str, Any]:
    for path in (PRIMARY_REGISTRY_FILE, LEGACY_REGISTRY_FILE):
        payload = load_json_file(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("providers"), list):
            return payload
        if isinstance(payload, list):
            return {"version": "phase0c", "providers": payload}
    return {"version": "phase0c", "providers": []}


def fetch_nvidia_models(raw: dict[str, str]) -> list[dict[str, Any]]:
    api_key = env_get(raw, "NVIDIA_API_KEY", "FREEWILLER_NVIDIA_API_KEY", "NGC_API_KEY", "NVIDIA_KIMI_K25_API_KEY")
    if not api_key:
        return []
    api_base_url = env_get(raw, "FREEWILLER_NVIDIA_API_BASE_URL", "NVIDIA_API_BASE_URL", default="https://integrate.api.nvidia.com/v1").rstrip("/")

    import urllib.request

    request = urllib.request.Request(
        f"{api_base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict):
        models = payload.get("data", [])
    else:
        models = payload
    if not isinstance(models, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        normalized.append(
            {
                "model": model_id,
                "owned_by": str(item.get("owned_by", "")).strip(),
                "created": item.get("created"),
                "discoverable_text_candidate": is_discoverable_nvidia_text_model(model_id),
                "discovered_at": utc_now(),
            }
        )
    return normalized


def fetch_openrouter_models(raw: dict[str, str]) -> list[dict[str, Any]]:
    api_key = env_get(raw, "FREEWILLER_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    if not api_key:
        return []
    api_base_url = env_get(raw, "FREEWILLER_OPENROUTER_API_BASE_URL", "OPENROUTER_API_BASE_URL", default="https://openrouter.ai/api/v1").rstrip("/")

    import urllib.request

    request = urllib.request.Request(
        f"{api_base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict):
        models = payload.get("data", [])
    else:
        models = payload
    if not isinstance(models, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        pricing = item.get("pricing", {}) if isinstance(item.get("pricing"), dict) else {}
        prompt_rate = parse_optional_float(pricing.get("prompt"))
        completion_rate = parse_optional_float(pricing.get("completion"))
        input_cache_read = parse_optional_float(pricing.get("input_cache_read"))
        free_candidate = (prompt_rate == 0.0 and completion_rate == 0.0) or model_id.endswith(":free")
        normalized_item = {
            "model": model_id,
            "name": str(item.get("name", "")).strip(),
            "owned_by": model_id.split("/", 1)[0] if "/" in model_id else "",
            "canonical_slug": str(item.get("canonical_slug", "")).strip(),
            "created": item.get("created"),
            "context_length": item.get("context_length"),
            "architecture": item.get("architecture"),
            "prompt_cost_per_million": (prompt_rate * 1_000_000) if prompt_rate is not None else None,
            "completion_cost_per_million": (completion_rate * 1_000_000) if completion_rate is not None else None,
            "cache_read_cost_per_million": (input_cache_read * 1_000_000) if input_cache_read is not None else None,
            "free_candidate": free_candidate,
            "discoverable_text_candidate": False,
            "discovered_at": utc_now(),
        }
        normalized_item["discoverable_text_candidate"] = is_discoverable_openrouter_text_model(normalized_item)
        normalized.append(normalized_item)
    return normalized


def discover_models(provider_family: str = "", sync: bool = False) -> dict[str, Any]:
    family = sanitize_provider_name(provider_family or "all") or "all"
    raw = load_raw_env()
    store = load_discovery_store()
    summaries: dict[str, Any] = {}

    if family in {"", "all", "nvidia"}:
        models = fetch_nvidia_models(raw)
        candidate_entries = [item for item in models if item.get("discoverable_text_candidate")]
        provider_payload = {
            "provider_family": "nvidia",
            "total_models": len(models),
            "candidate_models": len(candidate_entries),
            "models": models,
            "candidate_entries": candidate_entries,
            "updated_at": utc_now(),
        }
        store.setdefault("providers", {})["nvidia"] = provider_payload
        summaries["nvidia"] = {
            "total_models": len(models),
            "candidate_models": len(candidate_entries),
        }

    if family in {"", "all", "openrouter"}:
        models = fetch_openrouter_models(raw)
        candidate_entries = [item for item in models if item.get("discoverable_text_candidate")]
        provider_payload = {
            "provider_family": "openrouter",
            "total_models": len(models),
            "candidate_models": len(candidate_entries),
            "models": models,
            "candidate_entries": candidate_entries,
            "updated_at": utc_now(),
        }
        store.setdefault("providers", {})["openrouter"] = provider_payload
        summaries["openrouter"] = {
            "total_models": len(models),
            "candidate_models": len(candidate_entries),
        }

    save_discovery_store(store)
    if sync:
        sync_registry(write=True)
    return {
        "discovered_at": utc_now(),
        "providers": summaries,
        "discovery_file": str(DEFAULT_DISCOVERY_FILE),
        "registry_synced": bool(sync),
    }


def discovery_public_view(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_router_config()
    return {
        "updated_at": config.get("discovery_store", {}).get("updated_at", ""),
        "discovery_file": config["discovery_file"],
        "providers": config.get("discovery_store", {}).get("providers", {}),
    }


def sync_registry(write: bool = False) -> dict[str, Any]:
    raw = load_raw_env()
    current_payload = load_registry_payload()
    merged_entries = merge_registry_entries(current_payload.get("providers", []), default_registry_entries(raw))
    warnings = detect_repo_env_warnings()
    payload = {
        "version": "phase0c",
        "updated_at": utc_now(),
        "providers": merged_entries,
        "warnings": warnings,
    }
    if write:
        save_json_file(PRIMARY_REGISTRY_FILE, payload)
    return payload


def ensure_registry_synced() -> dict[str, Any]:
    if PRIMARY_REGISTRY_FILE.exists():
        payload = sync_registry(write=False)
        return payload
    return sync_registry(write=True)


def load_health_store() -> dict[str, Any]:
    payload = load_json_file(DEFAULT_HEALTH_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("providers"), dict):
        payload["providers"] = {}
    payload.setdefault("version", "phase0c")
    payload.setdefault("updated_at", "")
    return payload


def save_health_store(payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    save_json_file(DEFAULT_HEALTH_FILE, payload)


def load_benchmark_store() -> dict[str, Any]:
    payload = load_json_file(DEFAULT_BENCHMARKS_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("providers"), dict):
        payload["providers"] = {}
    payload.setdefault("version", "phase0c")
    payload.setdefault("updated_at", "")
    return payload


def save_benchmark_store(payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    save_json_file(DEFAULT_BENCHMARKS_FILE, payload)


def load_scorecard_store() -> dict[str, Any]:
    payload = load_json_file(DEFAULT_SCORECARDS_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("providers"), dict):
        payload["providers"] = {}
    if not isinstance(payload.get("leaders"), dict):
        payload["leaders"] = {}
    payload.setdefault("version", "phase0c")
    payload.setdefault("updated_at", "")
    payload.setdefault("source_usage_file", str(DEFAULT_USAGE_LEDGER_FILE))
    return payload


def save_scorecard_store(payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    save_json_file(DEFAULT_SCORECARDS_FILE, payload)


def load_discovery_store() -> dict[str, Any]:
    payload = load_json_file(DEFAULT_DISCOVERY_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("providers"), dict):
        payload["providers"] = {}
    payload.setdefault("version", "phase0c")
    payload.setdefault("updated_at", "")
    return payload


def save_discovery_store(payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    save_json_file(DEFAULT_DISCOVERY_FILE, payload)


def health_entry_default(provider_id: str, provider_enabled: bool) -> dict[str, Any]:
    state = "healthy" if provider_enabled else "disabled"
    return {
        "provider_id": provider_id,
        "state": state,
        "state_reason": "configured" if provider_enabled else "provider disabled in registry",
        "cooldown_until": "",
        "last_error": "",
        "last_checked_at": "",
        "last_success_at": "",
        "last_latency_ms": None,
        "successes": 0,
        "failures": 0,
        "success_rate": 0.0,
        "consecutive_failures": 0,
        "rate_limit_count": 0,
        "auth_error_count": 0,
    }


def classify_error_message(error_message: str) -> str:
    text = error_message.lower()
    if "429" in text or "rate limit" in text:
        return "rate_limited"
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text or "invalid api key" in text:
        return "auth_error"
    if "timed out" in text or "timeout" in text or "connection reset" in text or "remotedisconnected" in text:
        return "degraded"
    if re.search(r"http\s+5\d\d", text):
        return "degraded"
    return "degraded"


def record_provider_result(
    provider_id: str,
    *,
    provider_enabled: bool = True,
    ok: bool,
    latency_ms: int,
    error_message: str = "",
) -> dict[str, Any]:
    store = load_health_store()
    entry = dict(store["providers"].get(provider_id, health_entry_default(provider_id, provider_enabled)))
    entry["last_checked_at"] = utc_now()
    entry["last_latency_ms"] = latency_ms

    if ok:
        entry["successes"] = int(entry.get("successes", 0)) + 1
        total = int(entry.get("successes", 0)) + int(entry.get("failures", 0))
        entry["success_rate"] = round(entry["successes"] / max(total, 1), 4)
        entry["consecutive_failures"] = 0
        entry["state"] = "healthy" if provider_enabled else "disabled"
        entry["state_reason"] = "provider responded successfully" if provider_enabled else "provider disabled in registry"
        entry["cooldown_until"] = ""
        entry["last_error"] = ""
        entry["last_success_at"] = utc_now()
    else:
        error_kind = classify_error_message(error_message)
        entry["failures"] = int(entry.get("failures", 0)) + 1
        total = int(entry.get("successes", 0)) + int(entry.get("failures", 0))
        entry["success_rate"] = round(int(entry.get("successes", 0)) / max(total, 1), 4)
        entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
        entry["last_error"] = error_message

        if error_kind == "auth_error":
            entry["state"] = "auth_error"
            entry["state_reason"] = "provider authentication failed"
            entry["auth_error_count"] = int(entry.get("auth_error_count", 0)) + 1
            entry["cooldown_until"] = ""
        elif error_kind == "rate_limited":
            entry["state"] = "rate_limited"
            entry["state_reason"] = "provider rate limited recent requests"
            entry["rate_limit_count"] = int(entry.get("rate_limit_count", 0)) + 1
            entry["cooldown_until"] = (datetime.now(timezone.utc) + timedelta(seconds=COOLDOWN_SECONDS["rate_limited"])).isoformat()
        else:
            entry["state"] = "degraded"
            entry["state_reason"] = "provider request failed recently"
            entry["cooldown_until"] = (datetime.now(timezone.utc) + timedelta(seconds=COOLDOWN_SECONDS["degraded"])).isoformat()

    store["providers"][provider_id] = entry
    save_health_store(store)
    return entry


def provider_in_cooldown(health_entry: dict[str, Any]) -> bool:
    cooldown_until = parse_iso8601(str(health_entry.get("cooldown_until", "")))
    if not cooldown_until:
        return False
    return cooldown_until > datetime.now(timezone.utc)


def latency_score_from_ms(latency_ms: float | int | None) -> float:
    if not isinstance(latency_ms, (int, float)) or latency_ms <= 0:
        return 0.6
    return max(0.1, min(1.0, 1.0 / (1.0 + (float(latency_ms) / 4000.0))))


def refresh_scorecards(usage_ledger_file: str = "") -> dict[str, Any]:
    ledger_path = Path(usage_ledger_file or str(DEFAULT_USAGE_LEDGER_FILE))
    provider_records: dict[str, dict[str, Any]] = {}
    leaders: dict[str, dict[str, Any]] = {}

    lines: deque[str] = deque(maxlen=SCORECARD_WINDOW)
    if ledger_path.exists():
        with ledger_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)

    for raw_line in lines:
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        provider_id = sanitize_provider_name(str(event.get("provider_id", "")))
        task_class = normalize_task_class(str(event.get("task_class", "")))
        if not provider_id or not task_class:
            continue

        provider_card = provider_records.setdefault(provider_id, {"tasks": {}, "aggregate": {}})
        task_card = provider_card["tasks"].setdefault(
            task_class,
            {
                "total": 0,
                "ok": 0,
                "error": 0,
                "escalated": 0,
                "latencies": [],
                "costs": [],
                "last_used_at": "",
            },
        )

        task_card["total"] += 1
        status = str(event.get("status", "")).strip().lower()
        if status == "ok":
            task_card["ok"] += 1
        elif status == "escalated":
            task_card["ok"] += 1
            task_card["escalated"] += 1
        else:
            task_card["error"] += 1

        latency_ms = event.get("latency_ms")
        if isinstance(latency_ms, (int, float)) and latency_ms > 0:
            task_card["latencies"].append(float(latency_ms))

        estimated_cost = event.get("estimated_cost_usd")
        if isinstance(estimated_cost, (int, float)) and estimated_cost >= 0:
            task_card["costs"].append(float(estimated_cost))

        logged_at = str(event.get("logged_at", ""))
        if logged_at:
            task_card["last_used_at"] = logged_at

    for provider_id, provider_card in provider_records.items():
        aggregates = {"total": 0, "ok": 0, "error": 0, "escalated": 0, "latencies": [], "costs": [], "last_used_at": ""}
        for task_class, metrics in provider_card["tasks"].items():
            total = int(metrics["total"])
            ok = int(metrics["ok"])
            escalated = int(metrics["escalated"])
            avg_latency_ms = round(sum(metrics["latencies"]) / len(metrics["latencies"]), 2) if metrics["latencies"] else None
            success_rate = round(ok / max(total, 1), 4)
            escalation_rate = round(escalated / max(ok, 1), 4) if ok else 0.0
            avg_cost_usd = round(sum(metrics["costs"]) / len(metrics["costs"]), 8) if metrics["costs"] else None
            provider_card["tasks"][task_class] = {
                "total": total,
                "ok": ok,
                "error": int(metrics["error"]),
                "escalated": escalated,
                "success_rate": success_rate,
                "escalation_rate": escalation_rate,
                "avg_latency_ms": avg_latency_ms,
                "latency_score": round(latency_score_from_ms(avg_latency_ms), 4),
                "avg_cost_usd": avg_cost_usd,
                "last_used_at": metrics["last_used_at"],
            }
            aggregates["total"] += total
            aggregates["ok"] += ok
            aggregates["error"] += int(metrics["error"])
            aggregates["escalated"] += escalated
            if avg_latency_ms is not None:
                aggregates["latencies"].append(avg_latency_ms)
            if avg_cost_usd is not None:
                aggregates["costs"].append(avg_cost_usd)
            if metrics["last_used_at"]:
                aggregates["last_used_at"] = max(aggregates["last_used_at"], metrics["last_used_at"])

        aggregate_latency = round(sum(aggregates["latencies"]) / len(aggregates["latencies"]), 2) if aggregates["latencies"] else None
        aggregate_cost = round(sum(aggregates["costs"]) / len(aggregates["costs"]), 8) if aggregates["costs"] else None
        provider_card["aggregate"] = {
            "total": aggregates["total"],
            "ok": aggregates["ok"],
            "error": aggregates["error"],
            "escalated": aggregates["escalated"],
            "success_rate": round(aggregates["ok"] / max(aggregates["total"], 1), 4),
            "escalation_rate": round(aggregates["escalated"] / max(aggregates["ok"], 1), 4) if aggregates["ok"] else 0.0,
            "avg_latency_ms": aggregate_latency,
            "latency_score": round(latency_score_from_ms(aggregate_latency), 4),
            "avg_cost_usd": aggregate_cost,
            "last_used_at": aggregates["last_used_at"],
        }

    config = load_router_config()
    config = {**config, "scorecard_store": {"providers": provider_records, "leaders": {}}}
    for task_class in ("summarize", "extract", "compact", "reflect", "chat", "research_public"):
        try:
            ranking = choose_provider(task_class, task_class=task_class, privacy_class="public", _preloaded_config=config)
        except Exception:
            continue
        ranked = ranking.get("ranked_providers", [])
        leaders[task_class] = {
            "primary": ranked[0]["id"] if ranked else "",
            "backup": ranked[1]["id"] if len(ranked) > 1 else "",
            "updated_at": utc_now(),
        }

    payload = {
        "version": "phase0c",
        "source_usage_file": str(ledger_path),
        "providers": provider_records,
        "leaders": leaders,
    }
    save_scorecard_store(payload)
    return payload


def benchmark_quality_for(provider_id: str, task_class: str, benchmark_store: dict[str, Any], trust_tier: str) -> float:
    provider_entry = benchmark_store.get("providers", {}).get(provider_id, {})
    profiles = provider_entry.get("profiles", {})
    profile_name = TASK_PROFILE_MAP.get(task_class, "")
    if profile_name and isinstance(profiles.get(profile_name), dict):
        score = profiles[profile_name].get("score")
        if isinstance(score, (int, float)):
            return max(0.0, min(1.0, float(score)))
    aggregate = provider_entry.get("aggregate_quality")
    if isinstance(aggregate, (int, float)):
        return max(0.0, min(1.0, float(aggregate)))
    return DEFAULT_BENCHMARK_QUALITY.get(trust_tier, 0.5)


def task_fit_hint(provider: dict[str, Any], task_class: str, complexity_class: str = "") -> float:
    interactive = bool(provider.get("interactive", True))
    latency_tier = str(provider.get("latency_tier", "normal"))
    strength_tier = str(provider.get("strength_tier", "standard"))
    trust_tier = str(provider.get("trust_tier", "trusted_external"))
    resolved_complexity = normalize_complexity_class(complexity_class) or "medium"

    if trust_tier == "frontier":
        return 0.95
    if task_class in FAST_LOOP_TASKS:
        score = 0.55
        if interactive:
            score += 0.20
        if latency_tier == "normal":
            score += 0.15
        elif latency_tier == "slow":
            score -= 0.10
        if strength_tier in {"strong", "powerful"}:
            score += 0.05
        if resolved_complexity == "high":
            if strength_tier == "powerful":
                score += 0.12
            elif strength_tier == "strong":
                score += 0.08
            elif strength_tier == "standard":
                score -= 0.08
        elif resolved_complexity == "low":
            if strength_tier == "standard":
                score += 0.05
            if latency_tier == "slow":
                score -= 0.05
        return max(0.1, min(1.0, score))
    if task_class in SLOW_POWERFUL_TASKS:
        score = 0.45
        if strength_tier == "powerful":
            score += 0.28
        elif strength_tier == "strong":
            score += 0.20
        if latency_tier == "slow":
            score += 0.12
        elif latency_tier == "normal":
            score += 0.06
        if resolved_complexity == "high" and strength_tier == "powerful":
            score += 0.08
        elif resolved_complexity == "low" and latency_tier == "slow":
            score -= 0.06
        return max(0.1, min(1.0, score))
    return 0.6


def latency_score_for(health_entry: dict[str, Any]) -> float:
    latency_ms = health_entry.get("last_latency_ms")
    return latency_score_from_ms(latency_ms)


def cost_score_for(provider: dict[str, Any]) -> float:
    input_rate = provider.get("cost_input_per_million")
    output_rate = provider.get("cost_output_per_million")
    if isinstance(input_rate, (int, float)) or isinstance(output_rate, (int, float)):
        total_rate = float(input_rate or 0.0) + float(output_rate or 0.0)
        return max(0.05, min(1.0, 1.0 / (1.0 + total_rate / 6.0)))
    return DEFAULT_COST_SCORE.get(provider.get("trust_tier", "trusted_external"), 0.5)


def success_rate_for(health_entry: dict[str, Any], trust_tier: str) -> float:
    success_rate = health_entry.get("success_rate")
    if isinstance(success_rate, (int, float)) and success_rate > 0:
        return max(0.0, min(1.0, float(success_rate)))
    return DEFAULT_SUCCESS_RATE.get(trust_tier, 0.75)


def task_metrics_for(provider_id: str, task_class: str, scorecard_store: dict[str, Any]) -> dict[str, Any]:
    provider_card = scorecard_store.get("providers", {}).get(provider_id, {})
    task_metrics = provider_card.get("tasks", {}).get(task_class)
    if isinstance(task_metrics, dict):
        return task_metrics
    aggregate = provider_card.get("aggregate")
    if isinstance(aggregate, dict):
        return aggregate
    return {}


def benchmark_quality_for_task(
    provider: dict[str, Any],
    task_class: str,
    benchmark_store: dict[str, Any],
    complexity_class: str = "",
) -> float:
    trust_tier = provider.get("trust_tier", "trusted_external")
    base_quality = benchmark_quality_for(provider["id"], task_class, benchmark_store, trust_tier)
    fit_hint = task_fit_hint(provider, task_class, complexity_class)
    return round(max(0.0, min(1.0, (base_quality * 0.7) + (fit_hint * 0.3))), 4)


def provider_should_be_eligible(provider: dict[str, Any], task_class: str, privacy_class: str) -> tuple[bool, str]:
    if not provider.get("enabled", True):
        return False, "provider disabled"
    if not provider.get("configured", False):
        return False, "provider not configured"
    if privacy_class not in provider.get("allowed_privacy", []):
        return False, f"privacy class {privacy_class} not allowed"
    if task_class not in provider.get("allowed_tasks", []):
        return False, f"task class {task_class} not allowed"
    if not provider.get("interactive", True) and task_class in FAST_LOOP_TASKS:
        return False, f"provider reserved for slow powerful work, not {task_class}"

    health_entry = provider.get("health", {})
    state = health_entry.get("state", "healthy")
    if state in {"disabled", "auth_error"}:
        return False, f"provider state {state}"
    if provider_in_cooldown(health_entry):
        return False, f"provider cooling down until {health_entry.get('cooldown_until', '')}"
    return True, "eligible"


def provider_public_view(provider: dict[str, Any], *, include_score_components: bool = False) -> dict[str, Any]:
    brain_router_state = provider.get("brain_router_state", "eligible")
    roles = provider.get("brain_router_roles") or []
    if any(str(role).startswith("leader:") for role in roles):
        brain_router_state = "leader"
    if provider.get("health", {}).get("state") in {"degraded", "rate_limited", "auth_error"} and brain_router_state not in {"curated", "retired"}:
        brain_router_state = "degraded"
    view = {
        "id": provider["id"],
        "label": provider.get("label", provider["id"]),
        "kind": provider["kind"],
        "configured": provider.get("configured", False),
        "enabled": provider.get("enabled", True),
        "model": provider.get("model", ""),
        "provider_family": provider.get("provider_family", "generic"),
        "trust_tier": provider.get("trust_tier", "trusted_external"),
        "latency_tier": provider.get("latency_tier", "normal"),
        "strength_tier": provider.get("strength_tier", "standard"),
        "interactive": provider.get("interactive", True),
        "brain_router_state": brain_router_state,
        "allowed_privacy": provider.get("allowed_privacy", []),
        "allowed_tasks": provider.get("allowed_tasks", []),
        "max_output_tokens": provider.get("max_output_tokens"),
        "request_timeout_seconds": provider.get("request_timeout_seconds"),
        "health": {
            "state": provider.get("health", {}).get("state", "healthy"),
            "state_reason": provider.get("health", {}).get("state_reason", ""),
            "cooldown_until": provider.get("health", {}).get("cooldown_until", ""),
            "last_latency_ms": provider.get("health", {}).get("last_latency_ms"),
            "success_rate": provider.get("health", {}).get("success_rate"),
        },
    }
    if provider.get("api_base_url"):
        view["api_base_url"] = provider["api_base_url"]
    if provider.get("api_mode"):
        view["api_mode"] = provider["api_mode"]
    if provider.get("benchmark_profiles"):
        view["benchmark_profiles"] = provider["benchmark_profiles"]
    if isinstance(provider.get("scorecard"), dict):
        view["scorecard"] = provider["scorecard"]
    if roles:
        view["brain_router_roles"] = roles
    if provider.get("discovered_at"):
        view["discovered_at"] = provider["discovered_at"]
    if provider.get("discovery_source"):
        view["discovery_source"] = provider["discovery_source"]
    if provider.get("source_owned_by"):
        view["source_owned_by"] = provider["source_owned_by"]
    if provider.get("degraded_from_task_class"):
        view["degraded_from_task_class"] = provider["degraded_from_task_class"]
    if provider.get("fallback_scored_as"):
        view["fallback_scored_as"] = provider["fallback_scored_as"]
    if include_score_components and provider.get("score_components"):
        view["score"] = provider.get("score")
        view["score_components"] = provider.get("score_components")
    elif provider.get("score") is not None:
        view["score"] = provider.get("score")
    return view


def build_provider_config(raw: dict[str, str]) -> dict[str, Any]:
    registry_payload = ensure_registry_synced()
    health_store = load_health_store()
    benchmark_store = load_benchmark_store()
    scorecard_store = load_scorecard_store()
    discovery_store = load_discovery_store()
    default_privacy = normalize_privacy_class(env_get(raw, "FREEWILLER_ROUTER_DEFAULT_PRIVACY", default="internal")) or "internal"
    allow_public_external = env_bool(raw, "FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL", True)
    allow_internal_cheap = env_bool(raw, "FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP", True)
    allow_frontier_exhausted_fallback = env_bool(raw, "FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK", True)
    frontier_exhausted = env_bool(raw, "FREEWILLER_FRONTIER_EXHAUSTED", False)
    usage_ledger_file = normalize_usage_ledger_file(
        env_get(raw, "FREEWILLER_USAGE_LEDGER_FILE", default=str(DEFAULT_USAGE_LEDGER_FILE))
    )

    providers: dict[str, Any] = {}
    warnings = list(registry_payload.get("warnings", []))

    for raw_entry in registry_payload.get("providers", []):
        entry = normalize_provider_entry(raw_entry)
        if entry["kind"] == "gateway":
            configured = bool(
                env_get(raw, "FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL")
                and env_get(raw, "FREEWILLER_GATEWAY_TOKEN", "OPENCLAW_GATEWAY_TOKEN")
            )
            entry["api_base_url"] = env_get(raw, "FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL", default=entry["api_base_url"])
            entry["model"] = env_get(raw, "FREEWILLER_MODEL", "OPENCLAW_MODEL", default=entry["model"])
        else:
            api_key_env = entry.get("api_key_env", "")
            resolved_api_key = env_get(raw, api_key_env) if api_key_env else ""
            configured = bool(entry["api_base_url"] and entry["model"] and resolved_api_key)
            entry["api_key"] = resolved_api_key

        health_entry = dict(health_store.get("providers", {}).get(entry["id"], health_entry_default(entry["id"], entry["enabled"])))
        if not entry["enabled"]:
            health_entry["state"] = "disabled"
            health_entry["state_reason"] = "provider disabled in registry"
        entry["health"] = health_entry
        entry["configured"] = configured
        entry["scorecard"] = scorecard_store.get("providers", {}).get(entry["id"], {})
        entry["brain_router_roles"] = brain_router_roles_for(entry["id"], scorecard_store)
        providers[entry["id"]] = entry

    return {
        "policy_version": "phase0c",
        "default_privacy": default_privacy,
        "allow_public_external": allow_public_external,
        "allow_internal_cheap": allow_internal_cheap,
        "usage_ledger_file": usage_ledger_file,
        "registry_file": str(PRIMARY_REGISTRY_FILE),
        "health_file": str(DEFAULT_HEALTH_FILE),
        "benchmarks_file": str(DEFAULT_BENCHMARKS_FILE),
        "scorecards_file": str(DEFAULT_SCORECARDS_FILE),
        "discovery_file": str(DEFAULT_DISCOVERY_FILE),
        "warnings": warnings,
        "providers": providers,
        "health_store": health_store,
        "benchmark_store": benchmark_store,
        "scorecard_store": scorecard_store,
        "discovery_store": discovery_store,
        "allow_frontier_exhausted_fallback": allow_frontier_exhausted_fallback,
        "frontier_exhausted": frontier_exhausted,
    }


def load_router_config() -> dict[str, Any]:
    return build_provider_config(load_raw_env())


def summarize_rankings(config: dict[str, Any]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {}
    for task_class in ("summarize", "extract", "compact", "reflect", "chat", "research_public"):
        ranking = choose_provider(
            task_class.replace("_", " "),
            task_class=task_class,
            privacy_class="public",
            _preloaded_config=config,
        )
        summary[task_class] = [item["id"] for item in ranking["ranked_providers"]]
    return summary


def summarize_task_leaders(config: dict[str, Any]) -> dict[str, Any]:
    leaders = config.get("scorecard_store", {}).get("leaders", {})
    return {
        task_class: {
            "primary": info.get("primary", ""),
            "backup": info.get("backup", ""),
            "updated_at": info.get("updated_at", ""),
        }
        for task_class, info in sorted(leaders.items())
        if isinstance(info, dict)
    }


def brain_router_roles_for(provider_id: str, scorecard_store: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for task_class, info in scorecard_store.get("leaders", {}).items():
        if not isinstance(info, dict):
            continue
        if info.get("primary") == provider_id:
            roles.append(f"leader:{task_class}")
        if info.get("backup") == provider_id:
            roles.append(f"backup:{task_class}")
    return roles


def public_policy_view(config: dict[str, Any]) -> dict[str, Any]:
    discovery_summary = {}
    for family, info in config.get("discovery_store", {}).get("providers", {}).items():
        if not isinstance(info, dict):
            continue
        discovery_summary[family] = {
            "total_models": int(info.get("total_models", 0) or 0),
            "candidate_models": int(info.get("candidate_models", 0) or 0),
            "updated_at": info.get("updated_at", ""),
        }
    return {
        "policy_version": config["policy_version"],
        "default_privacy": config["default_privacy"],
        "allow_public_external": config["allow_public_external"],
        "allow_internal_cheap": config["allow_internal_cheap"],
        "allow_frontier_exhausted_fallback": config["allow_frontier_exhausted_fallback"],
        "frontier_exhausted": config["frontier_exhausted"],
        "usage_ledger_file": config["usage_ledger_file"],
        "registry_file": config["registry_file"],
        "health_file": config["health_file"],
        "benchmarks_file": config["benchmarks_file"],
        "scorecards_file": config["scorecards_file"],
        "discovery_file": config["discovery_file"],
        "warnings": config["warnings"],
        "ranking_summary": summarize_rankings(config),
        "task_leaders": summarize_task_leaders(config),
        "discovery_summary": discovery_summary,
        "providers": [provider_public_view(provider) for provider in config["providers"].values()],
    }


def build_score(
    provider: dict[str, Any],
    task_class: str,
    benchmark_store: dict[str, Any],
    scorecard_store: dict[str, Any],
    complexity_class: str = "",
) -> tuple[float, dict[str, float]]:
    trust_tier = provider.get("trust_tier", "trusted_external")
    task_metrics = task_metrics_for(provider["id"], task_class, scorecard_store)
    benchmark_quality = benchmark_quality_for_task(provider, task_class, benchmark_store, complexity_class)
    recent_success_rate = task_metrics.get("success_rate")
    if not isinstance(recent_success_rate, (int, float)):
        recent_success_rate = success_rate_for(provider.get("health", {}), trust_tier)
    latency_score = task_metrics.get("latency_score")
    if not isinstance(latency_score, (int, float)):
        latency_score = latency_score_for(provider.get("health", {}))
    cost_score = cost_score_for(provider)
    trust_score = TRUST_SCORE_MAP.get(trust_tier, 0.5)

    components = {
        "benchmark_quality": round(benchmark_quality, 4),
        "recent_success_rate": round(float(recent_success_rate), 4),
        "latency_score": round(float(latency_score), 4),
        "cost_score": round(cost_score, 4),
        "trust_score": round(trust_score, 4),
    }
    score = sum(components[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    return round(score, 4), components


def frontier_available(provider: dict[str, Any] | None, config: dict[str, Any]) -> bool:
    if config.get("frontier_exhausted", False):
        return False
    if not provider or not provider.get("configured", False):
        return False
    eligible, _ = provider_should_be_eligible(provider, "chat", "internal")
    return eligible


def selection_confidence_for(ranked_resolved: list[dict[str, Any]]) -> tuple[float, float]:
    if not ranked_resolved:
        return 0.0, 0.0
    top = float(ranked_resolved[0].get("score", 0.0))
    next_score = float(ranked_resolved[1].get("score", 0.0)) if len(ranked_resolved) > 1 else max(0.0, top - 0.20)
    gap = max(0.0, top - next_score)
    gap_score = min(1.0, gap / 0.12)
    confidence = max(0.0, min(1.0, (top * 0.65) + (gap_score * 0.35)))
    return round(confidence, 4), round(gap, 4)


def choose_provider(
    task: str,
    *,
    task_class: str = "",
    privacy_class: str = "",
    complexity_class: str = "",
    provider_override: str = "",
    _preloaded_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _preloaded_config or load_router_config()
    providers = config["providers"]
    resolved_task_class = normalize_task_class(task_class) or infer_task_class(task)
    resolved_privacy_class = normalize_privacy_class(privacy_class) or infer_privacy_class(task, config["default_privacy"])
    resolved_complexity_class = normalize_complexity_class(complexity_class) or (
        "high" if resolved_task_class in FRONTIER_ONLY_TASKS else "medium"
    )
    frontier_provider = providers.get("frontier_gateway")
    frontier_is_available = frontier_available(frontier_provider, config)

    if provider_override:
        override_id = sanitize_provider_name(provider_override)
        selected = providers.get(override_id)
        if not selected:
            raise RuntimeError(f"Unknown provider override: {provider_override}")
        eligible, reason = provider_should_be_eligible(selected, resolved_task_class, resolved_privacy_class)
        if not eligible:
            raise RuntimeError(f"Provider {override_id} is not eligible: {reason}")
        score, components = build_score(
            selected,
            resolved_task_class,
            config["benchmark_store"],
            config["scorecard_store"],
            resolved_complexity_class,
        )
        selected = {**selected, "score": score, "score_components": components}
        ranked_providers = [provider_public_view(selected, include_score_components=True)]
        reason_text = "explicit provider override"
        return {
            "policy_version": config["policy_version"],
            "task_class": resolved_task_class,
            "privacy_class": resolved_privacy_class,
            "complexity_class": resolved_complexity_class,
            "selected_provider": ranked_providers[0],
            "ranked_providers": ranked_providers,
            "reason": reason_text,
            "selection_confidence": 1.0,
            "score_gap_to_next": 1.0,
            "frontier_available": frontier_is_available,
            "frontier_exhausted_fallback": False,
            "escalate_on_low_confidence": False,
            "usage_ledger_file": config["usage_ledger_file"],
            "providers": [provider_public_view(provider) for provider in providers.values()],
            "warnings": config["warnings"],
        }

    non_frontier_candidates: list[dict[str, Any]] = []
    frontier_exhausted_candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for provider in providers.values():
        if provider["id"] == "frontier_gateway":
            continue

        if resolved_privacy_class == "public" and not config["allow_public_external"]:
            skipped.append({"id": provider["id"], "reason": "public external routing disabled"})
            continue

        if resolved_privacy_class == "internal" and not config["allow_internal_cheap"]:
            skipped.append({"id": provider["id"], "reason": "internal cheap routing disabled"})
            continue

        eligible, reason = provider_should_be_eligible(provider, resolved_task_class, resolved_privacy_class)
        if not eligible:
            if (
                resolved_task_class in FRONTIER_ONLY_TASKS
                and config["allow_frontier_exhausted_fallback"]
                and provider.get("enabled", True)
                and provider.get("configured", False)
                and resolved_privacy_class in provider.get("allowed_privacy", [])
            ):
                health_state = provider.get("health", {}).get("state", "healthy")
                if health_state not in {"disabled", "auth_error"} and not provider_in_cooldown(provider.get("health", {})):
                    fallback_task_class = "reflect" if resolved_task_class in {"architecture", "coding", "ops"} else resolved_task_class
                    score, components = build_score(
                        provider,
                        fallback_task_class,
                        config["benchmark_store"],
                        config["scorecard_store"],
                        resolved_complexity_class,
                    )
                    frontier_exhausted_candidates.append(
                        {
                            **provider,
                            "score": score,
                            "score_components": components,
                            "degraded_from_task_class": resolved_task_class,
                            "fallback_scored_as": fallback_task_class,
                        }
                    )
            skipped.append({"id": provider["id"], "reason": reason})
            continue

        score, components = build_score(
            provider,
            resolved_task_class,
            config["benchmark_store"],
            config["scorecard_store"],
            resolved_complexity_class,
        )
        non_frontier_candidates.append({**provider, "score": score, "score_components": components})

    non_frontier_candidates.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
    ranked_resolved: list[dict[str, Any]] = []

    if resolved_privacy_class in {"private", "secret"}:
        if not frontier_provider or not frontier_provider.get("configured", False):
            raise RuntimeError("Frontier gateway is required for private/secret tasks")
        if not frontier_is_available:
            raise RuntimeError("Frontier gateway is unavailable for private/secret tasks")
        frontier_score, frontier_components = build_score(
            frontier_provider,
            resolved_task_class,
            config["benchmark_store"],
            config["scorecard_store"],
            resolved_complexity_class,
        )
        ranked_resolved = [{**frontier_provider, "score": frontier_score, "score_components": frontier_components}]
        reason_text = f"{resolved_privacy_class} data stays on the frontier lane"
        return {
            "policy_version": config["policy_version"],
            "task_class": resolved_task_class,
            "privacy_class": resolved_privacy_class,
            "complexity_class": resolved_complexity_class,
            "selected_provider": provider_public_view(ranked_resolved[0], include_score_components=True),
            "ranked_providers": [provider_public_view(item, include_score_components=True) for item in ranked_resolved],
            "reason": reason_text,
            "selection_confidence": 1.0,
            "score_gap_to_next": 1.0,
            "frontier_available": frontier_is_available,
            "frontier_exhausted_fallback": False,
            "escalate_on_low_confidence": False,
            "usage_ledger_file": config["usage_ledger_file"],
            "providers": [provider_public_view(provider) for provider in providers.values()],
            "warnings": config["warnings"],
            "skipped_providers": skipped,
        }

    frontier_candidate: dict[str, Any] | None = None
    if frontier_provider and frontier_provider.get("configured", False):
        frontier_score, frontier_components = build_score(
            frontier_provider,
            resolved_task_class,
            config["benchmark_store"],
            config["scorecard_store"],
            resolved_complexity_class,
        )
        frontier_candidate = {**frontier_provider, "score": frontier_score, "score_components": frontier_components}

    if resolved_task_class in FRONTIER_ONLY_TASKS:
        if frontier_is_available and frontier_candidate:
            ranked_resolved = [frontier_candidate]
            if config["allow_frontier_exhausted_fallback"] and non_frontier_candidates:
                ranked_resolved.extend(non_frontier_candidates)
            reason_text = f"{resolved_task_class} tasks prefer the frontier lane"
        elif config["allow_frontier_exhausted_fallback"] and frontier_exhausted_candidates:
            frontier_exhausted_candidates.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
            ranked_resolved = list(frontier_exhausted_candidates)
            reason_text = f"{resolved_task_class} tasks degraded to non-frontier fallback because the frontier lane is unavailable"
        else:
            raise RuntimeError(f"Frontier gateway is unavailable for {resolved_task_class} tasks")
    else:
        ranked_resolved = list(non_frontier_candidates)
        if frontier_candidate and frontier_is_available:
            ranked_resolved.append(frontier_candidate)

    if not ranked_resolved:
        raise RuntimeError("No configured provider is eligible for this task")

    selected_provider = ranked_resolved[0]
    selection_confidence, score_gap_to_next = selection_confidence_for(ranked_resolved)
    frontier_exhausted_fallback = (
        resolved_task_class in FRONTIER_ONLY_TASKS
        and selected_provider["id"] != "frontier_gateway"
    )
    escalate_on_low_confidence = (
        selected_provider["id"] != "frontier_gateway"
        and frontier_is_available
        and resolved_task_class in FRONTIER_REVIEW_TASKS
        and (selection_confidence < FRONTIER_REVIEW_CONFIDENCE_THRESHOLD or score_gap_to_next < SMALL_GAP_THRESHOLD)
    )

    if resolved_task_class not in FRONTIER_ONLY_TASKS:
        if selected_provider["id"] == "frontier_gateway":
            reason_text = "defaulting to the frontier lane"
        elif frontier_is_available:
            reason_text = "ranked eligible non-frontier providers first with frontier fallback"
        else:
            reason_text = "ranked eligible non-frontier providers while the frontier lane is unavailable"

    return {
        "policy_version": config["policy_version"],
        "task_class": resolved_task_class,
        "privacy_class": resolved_privacy_class,
        "complexity_class": resolved_complexity_class,
        "selected_provider": provider_public_view(selected_provider, include_score_components=True),
        "ranked_providers": [provider_public_view(item, include_score_components=True) for item in ranked_resolved],
        "reason": reason_text,
        "selection_confidence": selection_confidence,
        "score_gap_to_next": score_gap_to_next,
        "frontier_available": frontier_is_available,
        "frontier_exhausted_fallback": frontier_exhausted_fallback,
        "escalate_on_low_confidence": escalate_on_low_confidence,
        "usage_ledger_file": config["usage_ledger_file"],
        "providers": [provider_public_view(provider) for provider in providers.values()],
        "warnings": config["warnings"],
        "skipped_providers": skipped,
    }


def normalize_usage(raw_usage: dict[str, Any] | None) -> dict[str, int]:
    raw_usage = raw_usage or {}
    input_tokens = raw_usage.get("input_tokens", raw_usage.get("prompt_tokens", 0)) or 0
    output_tokens = raw_usage.get("output_tokens", raw_usage.get("completion_tokens", 0)) or 0
    total_tokens = raw_usage.get("total_tokens", input_tokens + output_tokens) or 0
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
    }


def estimate_cost_usd(provider_id: str, usage: dict[str, int]) -> float | None:
    config = load_router_config()
    provider = config["providers"].get(provider_id)
    if not provider:
        return None

    input_rate = provider.get("cost_input_per_million")
    output_rate = provider.get("cost_output_per_million")
    if input_rate is None and output_rate is None:
        return None

    input_cost = (usage.get("input_tokens", 0) / 1_000_000) * float(input_rate or 0.0)
    output_cost = (usage.get("output_tokens", 0) / 1_000_000) * float(output_rate or 0.0)
    return round(input_cost + output_cost, 8)


def append_usage_ledger(entry: dict[str, Any]) -> str:
    config = load_router_config()
    ledger_path = Path(config["usage_ledger_file"])
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"logged_at": utc_now(), **entry}
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    refresh_scorecards(str(ledger_path))
    return str(ledger_path)


def load_benchmark_profiles(profile_name: str = "") -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    if not BENCHMARKS_DIR.exists():
        return profiles

    for path in sorted(BENCHMARKS_DIR.glob("*.json")):
        payload = load_json_file(path, {})
        if not isinstance(payload, dict):
            continue
        profile = str(payload.get("profile", path.stem)).strip().lower()
        if profile_name and profile != profile_name:
            continue
        payload["profile"] = profile
        profiles.append(payload)
    return profiles


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def evaluate_case_output(output_text: str, case: dict[str, Any]) -> dict[str, Any]:
    normalized_output = normalize_text(output_text)
    details: dict[str, Any] = {
        "output_chars": len(output_text),
        "matched_all": [],
        "matched_any": [],
        "missing_all": [],
        "missing_any": [],
        "forbidden_hits": [],
        "json_keys_present": [],
        "json_keys_missing": [],
    }
    score = 1.0

    expected_all = [normalize_text(str(item)) for item in case.get("expected_all", [])]
    expected_any = [normalize_text(str(item)) for item in case.get("expected_any", [])]
    forbidden = [normalize_text(str(item)) for item in case.get("forbidden", [])]
    max_chars = int(case.get("max_chars", 0) or 0)
    required_json_keys = [str(item) for item in case.get("require_json_keys", [])]

    if expected_all:
        matched = [item for item in expected_all if item in normalized_output]
        missing = [item for item in expected_all if item not in normalized_output]
        details["matched_all"] = matched
        details["missing_all"] = missing
        score *= len(matched) / len(expected_all)

    if expected_any:
        matched = [item for item in expected_any if item in normalized_output]
        details["matched_any"] = matched
        if matched:
            score *= 1.0
        else:
            details["missing_any"] = expected_any
            score *= 0.4

    for item in forbidden:
        if item and item in normalized_output:
            details["forbidden_hits"].append(item)
            score *= 0.65

    if max_chars and len(output_text) > max_chars:
        overflow_ratio = min(1.0, (len(output_text) - max_chars) / max_chars)
        score *= max(0.35, 1.0 - overflow_ratio)

    if required_json_keys:
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            present = [key for key in required_json_keys if key in parsed]
            missing = [key for key in required_json_keys if key not in parsed]
            details["json_keys_present"] = present
            details["json_keys_missing"] = missing
            score *= len(present) / len(required_json_keys)
        else:
            details["json_keys_missing"] = required_json_keys
            score *= 0.25

    score = max(0.0, min(1.0, score))
    details["score"] = round(score, 4)
    return details


def dispatch_with_provider_override(provider_id: str, task: str, task_class: str, privacy_class: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "python3",
            str(LOCAL_AGENT_PY),
            "dispatch",
            "--task",
            task,
            "--task-class",
            task_class,
            "--privacy-class",
            privacy_class,
            "--provider",
            provider_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or f"dispatch failed with code {result.returncode}"
        raise RuntimeError(stderr)
    return json.loads(result.stdout)


def frontier_judge_score(profile: dict[str, Any], case: dict[str, Any], output_text: str) -> dict[str, Any]:
    rubric = {
        "profile": profile["profile"],
        "task_class": profile.get("task_class", profile["profile"]),
        "expected_all": case.get("expected_all", []),
        "expected_any": case.get("expected_any", []),
        "forbidden": case.get("forbidden", []),
        "require_json_keys": case.get("require_json_keys", []),
        "max_chars": case.get("max_chars", 0),
    }
    judge_task = (
        "You are grading another model output. Return JSON only in the form "
        '{"score": <0-100>, "reason": "<short reason>"}. '
        "Score for faithfulness, format compliance, compactness, and usefulness.\n\n"
        f"Benchmark case:\n{json.dumps(rubric, ensure_ascii=True)}\n\n"
        f"Original task:\n{case.get('task', '').strip()}\n\n"
        f"Candidate output:\n{output_text.strip()}"
    )

    result = dispatch_with_provider_override("frontier_gateway", judge_task, "classify", "internal")
    raw_text = result.get("provider_response_text", "").strip()
    try:
        payload = json.loads(raw_text)
        score = float(payload.get("score", 0.0))
        reason = str(payload.get("reason", "")).strip()
    except json.JSONDecodeError:
        match = re.search(r"(\d{1,3})", raw_text)
        score = float(match.group(1)) if match else 0.0
        reason = raw_text[:240]

    normalized_score = max(0.0, min(1.0, score / 100.0))
    return {
        "score": round(normalized_score, 4),
        "reason": reason,
        "raw_response": raw_text,
    }


def should_use_frontier_judge(provider_id: str, profile_name: str, judge_mode: str, benchmark_store: dict[str, Any]) -> bool:
    mode = judge_mode.strip().lower()
    if mode == "never":
        return False
    if provider_id == "frontier_gateway":
        return False
    if mode == "always":
        return True

    provider_profiles = benchmark_store.get("providers", {}).get(provider_id, {}).get("profiles", {})
    existing_profile = provider_profiles.get(profile_name, {})
    last_evaluated = parse_iso8601(str(existing_profile.get("last_evaluated_at", "")))
    if not existing_profile:
        return True
    if not last_evaluated:
        return True
    return last_evaluated < datetime.now(timezone.utc) - timedelta(hours=24)


def evaluate_provider_profile(provider: dict[str, Any], profile: dict[str, Any], judge_mode: str, benchmark_store: dict[str, Any]) -> dict[str, Any]:
    task_class = normalize_task_class(str(profile.get("task_class", profile["profile"]))) or "chat"
    privacy_class = normalize_privacy_class(str(profile.get("privacy_class", "public"))) or "public"
    cases = profile.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise RuntimeError(f"Benchmark profile {profile['profile']} has no cases")

    case_results: list[dict[str, Any]] = []
    for case in cases:
        case_name = str(case.get("name", "unnamed"))
        task = str(case.get("task", "")).strip()
        if not task:
            raise RuntimeError(f"Benchmark case {case_name} in profile {profile['profile']} is missing task")

        dispatch_result = dispatch_with_provider_override(provider["id"], task, task_class, privacy_class)
        output_text = dispatch_result.get("provider_response_text", "")
        heuristic = evaluate_case_output(output_text, case)
        case_result: dict[str, Any] = {
            "name": case_name,
            "heuristic_score": heuristic["score"],
            "details": heuristic,
            "provider_response_text": output_text,
            "selected_provider": dispatch_result.get("provider_plan", {}).get("selected_provider", {}).get("id", provider["id"]),
            "latency_ms": dispatch_result.get("provider_plan", {}).get("selected_provider", {}).get("health", {}).get("last_latency_ms"),
        }

        if should_use_frontier_judge(provider["id"], profile["profile"], judge_mode, benchmark_store):
            judge_result = frontier_judge_score(profile, case, output_text)
            case_result["judge_score"] = judge_result["score"]
            case_result["judge_reason"] = judge_result["reason"]
            case_result["judge_raw_response"] = judge_result["raw_response"]
            case_result["score"] = round((heuristic["score"] * 0.5) + (judge_result["score"] * 0.5), 4)
        else:
            case_result["score"] = heuristic["score"]

        case_results.append(case_result)

    average_score = round(sum(case["score"] for case in case_results) / len(case_results), 4)
    average_heuristic = round(sum(case["heuristic_score"] for case in case_results) / len(case_results), 4)
    judge_scores = [case["judge_score"] for case in case_results if isinstance(case.get("judge_score"), (int, float))]
    average_judge = round(sum(judge_scores) / len(judge_scores), 4) if judge_scores else None

    return {
        "profile": profile["profile"],
        "task_class": task_class,
        "privacy_class": privacy_class,
        "score": average_score,
        "heuristic_score": average_heuristic,
        "judge_score": average_judge,
        "case_count": len(case_results),
        "cases": case_results,
        "last_evaluated_at": utc_now(),
    }


def evaluate_providers(provider_id: str = "", profile_name: str = "", judge_mode: str = "targeted") -> dict[str, Any]:
    config = load_router_config()
    profiles = load_benchmark_profiles(profile_name)
    if profile_name and not profiles:
        raise RuntimeError(f"Unknown benchmark profile: {profile_name}")

    benchmark_store = load_benchmark_store()
    eligible_providers = []
    for provider in config["providers"].values():
        if provider_id and provider["id"] != sanitize_provider_name(provider_id):
            continue
        if not provider.get("configured", False):
            continue
        eligible_providers.append(provider)

    if provider_id and not eligible_providers:
        raise RuntimeError(f"Provider {provider_id} is not configured")

    summaries: list[dict[str, Any]] = []
    for provider in eligible_providers:
        provider_profiles = [profile for profile in profiles if profile["profile"] in provider.get("benchmark_profiles", [])]
        if not provider_profiles:
            continue

        provider_summary = benchmark_store.get("providers", {}).get(provider["id"], {})
        updated_profiles: dict[str, Any] = dict(provider_summary.get("profiles", {}))
        profile_summaries: list[dict[str, Any]] = []
        for profile in provider_profiles:
            result = evaluate_provider_profile(provider, profile, judge_mode, benchmark_store)
            updated_profiles[profile["profile"]] = result
            profile_summaries.append(result)

        aggregate_quality = round(
            sum(profile_result["score"] for profile_result in updated_profiles.values() if isinstance(profile_result, dict))
            / max(len([profile_result for profile_result in updated_profiles.values() if isinstance(profile_result, dict)]), 1),
            4,
        )
        benchmark_store.setdefault("providers", {})[provider["id"]] = {
            "profiles": updated_profiles,
            "aggregate_quality": aggregate_quality,
            "last_evaluated_at": utc_now(),
        }
        summaries.append(
            {
                "provider_id": provider["id"],
                "aggregate_quality": aggregate_quality,
                "profiles": profile_summaries,
            }
        )

    save_benchmark_store(benchmark_store)
    return {
        "evaluated_at": utc_now(),
        "judge_mode": judge_mode,
        "profiles": [profile["profile"] for profile in profiles],
        "providers": summaries,
        "benchmarks_file": str(DEFAULT_BENCHMARKS_FILE),
    }


def heartbeat_provider(provider: dict[str, Any]) -> dict[str, Any]:
    if provider["id"] == "frontier_gateway":
        gateway_url = provider.get("api_base_url", "").rstrip("/")
        if not gateway_url:
            raise RuntimeError("Frontier gateway URL is not configured")

        import urllib.request

        started_at = datetime.now(timezone.utc)
        with urllib.request.urlopen(f"{gateway_url}/healthz", timeout=10) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Gateway health returned HTTP {response.status}")
        latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        entry = record_provider_result(provider["id"], provider_enabled=provider.get("enabled", True), ok=True, latency_ms=latency_ms)
        return {"provider_id": provider["id"], "status": "ok", "latency_ms": latency_ms, "health": entry}

    dispatch_result = dispatch_with_provider_override(
        provider["id"],
        "Reply with the single word HEALTHY.",
        "chat",
        "public",
    )
    return {
        "provider_id": provider["id"],
        "status": "ok",
        "response_text": dispatch_result.get("provider_response_text", ""),
        "usage": dispatch_result.get("usage", {}),
    }


def heartbeat_providers(provider_id: str = "") -> dict[str, Any]:
    config = load_router_config()
    summaries: list[dict[str, Any]] = []
    for provider in config["providers"].values():
        if provider_id and provider["id"] != sanitize_provider_name(provider_id):
            continue
        if not provider.get("enabled", True):
            continue
        if not provider.get("configured", False):
            continue
        try:
            summaries.append(heartbeat_provider(provider))
        except Exception as exc:
            latency_ms = int(provider.get("health", {}).get("last_latency_ms") or 0)
            entry = record_provider_result(provider["id"], provider_enabled=provider.get("enabled", True), ok=False, latency_ms=latency_ms, error_message=str(exc))
            summaries.append({"provider_id": provider["id"], "status": "error", "error": str(exc), "health": entry})
    return {"checked_at": utc_now(), "providers": summaries, "health_file": str(DEFAULT_HEALTH_FILE)}


def health_public_view(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_router_config()
    return {
        "checked_at": utc_now(),
        "health_file": config["health_file"],
        "providers": {
            provider_id: {
                "label": provider.get("label", provider_id),
                "configured": provider.get("configured", False),
                "enabled": provider.get("enabled", True),
                "trust_tier": provider.get("trust_tier", "trusted_external"),
                "health": provider.get("health", {}),
            }
            for provider_id, provider in config["providers"].items()
        },
    }


def scorecards_public_view(refresh: bool = False) -> dict[str, Any]:
    config = load_router_config()
    if refresh:
        refresh_scorecards(config["usage_ledger_file"])
        config = load_router_config()
    payload = config.get("scorecard_store", {})
    return {
        "updated_at": payload.get("updated_at", ""),
        "scorecards_file": config["scorecards_file"],
        "leaders": payload.get("leaders", {}),
        "providers": payload.get("providers", {}),
    }


def discover_command(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            discover_models(provider_family=args.provider_family, sync=args.sync),
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


def discovery_command(_args: argparse.Namespace) -> int:
    print(json.dumps(discovery_public_view(), indent=2, ensure_ascii=True))
    return 0


def sync_command(_args: argparse.Namespace) -> int:
    payload = sync_registry(write=True)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def policy_command(_args: argparse.Namespace) -> int:
    print(json.dumps(public_policy_view(load_router_config()), indent=2, ensure_ascii=True))
    return 0


def providers_command(_args: argparse.Namespace) -> int:
    config = load_router_config()
    print(json.dumps(public_policy_view(config), indent=2, ensure_ascii=True))
    return 0


def rank_command(args: argparse.Namespace) -> int:
    task = args.task or args.task_class or "chat"
    print(
        json.dumps(
            choose_provider(
                task,
                task_class=args.task_class,
                privacy_class=args.privacy_class,
                provider_override=args.provider,
            ),
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


def evaluate_command(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            evaluate_providers(
                provider_id=args.provider,
                profile_name=args.profile,
                judge_mode=args.judge_mode,
            ),
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


def health_command(args: argparse.Namespace) -> int:
    if args.refresh:
        print(json.dumps(heartbeat_providers(provider_id=args.provider), indent=2, ensure_ascii=True))
        return 0
    print(json.dumps(health_public_view(), indent=2, ensure_ascii=True))
    return 0


def heartbeat_command(args: argparse.Namespace) -> int:
    print(json.dumps(heartbeat_providers(provider_id=args.provider), indent=2, ensure_ascii=True))
    return 0


def scorecards_command(args: argparse.Namespace) -> int:
    print(json.dumps(scorecards_public_view(refresh=args.refresh), indent=2, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genie Brain provider registry, routing, health, and benchmarks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.set_defaults(func=sync_command)

    policy_parser = subparsers.add_parser("policy")
    policy_parser.set_defaults(func=policy_command)

    providers_parser = subparsers.add_parser("providers")
    providers_parser.set_defaults(func=providers_command)

    discovery_parser = subparsers.add_parser("discovery")
    discovery_parser.set_defaults(func=discovery_command)

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--provider-family", default="all")
    discover_parser.add_argument("--sync", action="store_true")
    discover_parser.set_defaults(func=discover_command)

    rank_parser = subparsers.add_parser("rank")
    rank_parser.add_argument("--task", default="")
    rank_parser.add_argument("--task-class", default="")
    rank_parser.add_argument("--privacy-class", default="")
    rank_parser.add_argument("--provider", default="")
    rank_parser.set_defaults(func=rank_command)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--task", default="")
    plan_parser.add_argument("--task-class", default="")
    plan_parser.add_argument("--privacy-class", default="")
    plan_parser.add_argument("--provider", default="")
    plan_parser.set_defaults(func=rank_command)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--provider", default="")
    evaluate_parser.add_argument("--profile", default="")
    evaluate_parser.add_argument("--judge-mode", default="targeted", choices=["targeted", "always", "never"])
    evaluate_parser.set_defaults(func=evaluate_command)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--provider", default="")
    health_parser.add_argument("--refresh", action="store_true")
    health_parser.set_defaults(func=health_command)

    heartbeat_parser = subparsers.add_parser("heartbeat")
    heartbeat_parser.add_argument("--provider", default="")
    heartbeat_parser.set_defaults(func=heartbeat_command)

    scorecards_parser = subparsers.add_parser("scorecards")
    scorecards_parser.add_argument("--refresh", action="store_true")
    scorecards_parser.set_defaults(func=scorecards_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
