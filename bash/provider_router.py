#!/usr/bin/env python3

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIMARY_ROUTER_ENV_BASENAME = "provider-routing.env"
LEGACY_ROUTER_ENV_BASENAME = "provider-router.env"
PRIMARY_GATEWAY_ENV_BASENAME = "freewiller-gateway.env"
LEGACY_GATEWAY_ENV_BASENAME = "openclaw-gateway.env"

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
PUBLIC_ELIGIBLE_TASKS = {"summarize", "extract", "classify", "compact", "reflect", "research_public"}
CHEAP_ELIGIBLE_TASKS = PUBLIC_ELIGIBLE_TASKS | {"chat"}
FRONTIER_ONLY_TASKS = {"architecture", "coding", "ops"}


def resolve_state_dir() -> Path:
    if os.environ.get("LOCAL_LLM_DIR"):
        return Path(os.environ["LOCAL_LLM_DIR"])
    default_path = Path("/local/state/freewiller")
    primary_legacy_path = Path("/var/lib/freewiller")
    secondary_legacy_path = Path("/var/lib/openclaw-local-llm")
    if default_path.exists():
        return default_path
    if primary_legacy_path.exists():
        return primary_legacy_path
    if secondary_legacy_path.exists():
        return secondary_legacy_path
    return default_path


LOCAL_LLM_DIR = resolve_state_dir()
PRIMARY_ROUTER_ENV_FILE = LOCAL_LLM_DIR / PRIMARY_ROUTER_ENV_BASENAME
LEGACY_ROUTER_ENV_FILE = LOCAL_LLM_DIR / LEGACY_ROUTER_ENV_BASENAME
PRIMARY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / PRIMARY_GATEWAY_ENV_BASENAME
LEGACY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / LEGACY_GATEWAY_ENV_BASENAME
TELEMETRY_DIR = LOCAL_LLM_DIR / "telemetry"
DEFAULT_USAGE_LEDGER_FILE = TELEMETRY_DIR / "provider-usage.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def load_raw_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (
        PRIMARY_ROUTER_ENV_FILE,
        LEGACY_ROUTER_ENV_FILE,
        PRIMARY_GATEWAY_ENV_FILE,
        LEGACY_GATEWAY_ENV_FILE,
    ):
        values.update(parse_env_file(path))

    for key, value in os.environ.items():
        if key.startswith("FREEWILLER_") or key.startswith("OPENCLAW_"):
            values[key] = value
    return values


def env_get(raw: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return value
    return default


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


def build_provider_config(raw: dict[str, str]) -> dict[str, Any]:
    default_privacy = normalize_privacy_class(env_get(raw, "FREEWILLER_ROUTER_DEFAULT_PRIVACY", default="internal")) or "internal"
    allow_public_external = env_bool(raw, "FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL", True)
    allow_internal_cheap = env_bool(raw, "FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP", True)
    usage_ledger_file = env_get(raw, "FREEWILLER_USAGE_LEDGER_FILE", default=str(DEFAULT_USAGE_LEDGER_FILE))

    cheap_allowed_privacy = ["public", "internal"] if allow_internal_cheap else ["public"]

    providers = {
        "frontier_gateway": {
            "id": "frontier_gateway",
            "label": "Frontier Gateway",
            "kind": "gateway",
            "provider_family": "frontier",
            "configured": bool(
                env_get(raw, "FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL")
                and env_get(raw, "FREEWILLER_GATEWAY_TOKEN", "OPENCLAW_GATEWAY_TOKEN")
            ),
            "model": env_get(raw, "FREEWILLER_MODEL", "OPENCLAW_MODEL", default="openclaw:main"),
            "allowed_privacy": ["public", "internal", "private", "secret"],
            "max_output_tokens": env_int(
                raw,
                "FREEWILLER_MAX_OUTPUT_TOKENS",
                env_int(raw, "OPENCLAW_MAX_OUTPUT_TOKENS", 2048),
            ),
            "api_base_url": env_get(raw, "FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL"),
            "input_cost_per_million": env_float(raw, "FREEWILLER_FRONTIER_INPUT_COST_PER_MILLION"),
            "output_cost_per_million": env_float(raw, "FREEWILLER_FRONTIER_OUTPUT_COST_PER_MILLION"),
        },
        "cheap_openai": {
            "id": "cheap_openai",
            "label": "Cheap Compatible",
            "kind": "openai_compatible",
            "provider_family": env_get(raw, "FREEWILLER_CHEAP_PROVIDER_FAMILY", default="generic"),
            "configured": bool(
                env_get(raw, "FREEWILLER_CHEAP_API_BASE_URL")
                and env_get(raw, "FREEWILLER_CHEAP_API_KEY")
                and env_get(raw, "FREEWILLER_CHEAP_MODEL")
            ),
            "model": env_get(raw, "FREEWILLER_CHEAP_MODEL"),
            "allowed_privacy": cheap_allowed_privacy,
            "max_output_tokens": env_int(raw, "FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS", 1024),
            "api_base_url": env_get(raw, "FREEWILLER_CHEAP_API_BASE_URL"),
            "api_key": env_get(raw, "FREEWILLER_CHEAP_API_KEY"),
            "api_mode": env_get(raw, "FREEWILLER_CHEAP_API_MODE", default="chat").strip().lower() or "chat",
            "extra_body_json": env_get(raw, "FREEWILLER_CHEAP_EXTRA_BODY_JSON"),
            "input_cost_per_million": env_float(raw, "FREEWILLER_CHEAP_INPUT_COST_PER_MILLION"),
            "output_cost_per_million": env_float(raw, "FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION"),
        },
        "public_openai": {
            "id": "public_openai",
            "label": "Public External",
            "kind": "openai_compatible",
            "provider_family": env_get(raw, "FREEWILLER_PUBLIC_PROVIDER_FAMILY", default="generic"),
            "configured": bool(
                env_get(raw, "FREEWILLER_PUBLIC_API_BASE_URL")
                and env_get(raw, "FREEWILLER_PUBLIC_API_KEY")
                and env_get(raw, "FREEWILLER_PUBLIC_MODEL")
            ),
            "model": env_get(raw, "FREEWILLER_PUBLIC_MODEL"),
            "allowed_privacy": ["public"],
            "max_output_tokens": env_int(raw, "FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS", 1024),
            "api_base_url": env_get(raw, "FREEWILLER_PUBLIC_API_BASE_URL"),
            "api_key": env_get(raw, "FREEWILLER_PUBLIC_API_KEY"),
            "api_mode": env_get(raw, "FREEWILLER_PUBLIC_API_MODE", default="chat").strip().lower() or "chat",
            "extra_body_json": env_get(raw, "FREEWILLER_PUBLIC_EXTRA_BODY_JSON"),
            "input_cost_per_million": env_float(raw, "FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION"),
            "output_cost_per_million": env_float(raw, "FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION"),
        },
    }

    return {
        "policy_version": "phase0a",
        "default_privacy": default_privacy,
        "allow_public_external": allow_public_external,
        "allow_internal_cheap": allow_internal_cheap,
        "usage_ledger_file": usage_ledger_file,
        "providers": providers,
    }


def load_router_config() -> dict[str, Any]:
    return build_provider_config(load_raw_env())


def provider_public_view(provider: dict[str, Any]) -> dict[str, Any]:
    view = {
        "id": provider["id"],
        "label": provider["label"],
        "kind": provider["kind"],
        "configured": provider["configured"],
        "model": provider.get("model", ""),
        "allowed_privacy": provider.get("allowed_privacy", []),
        "max_output_tokens": provider.get("max_output_tokens"),
    }
    if provider.get("api_base_url"):
        view["api_base_url"] = provider["api_base_url"]
    if provider.get("api_mode"):
        view["api_mode"] = provider["api_mode"]
    if provider.get("provider_family"):
        view["provider_family"] = provider["provider_family"]
    return view


def public_policy_view(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": config["policy_version"],
        "default_privacy": config["default_privacy"],
        "allow_public_external": config["allow_public_external"],
        "allow_internal_cheap": config["allow_internal_cheap"],
        "usage_ledger_file": config["usage_ledger_file"],
        "providers": [provider_public_view(provider) for provider in config["providers"].values()],
    }


def choose_provider(
    task: str,
    *,
    task_class: str = "",
    privacy_class: str = "",
    provider_override: str = "",
) -> dict[str, Any]:
    config = load_router_config()
    providers = config["providers"]
    resolved_task_class = normalize_task_class(task_class) or infer_task_class(task)
    resolved_privacy_class = normalize_privacy_class(privacy_class) or infer_privacy_class(task, config["default_privacy"])

    if provider_override:
        override_id = sanitize_provider_name(provider_override)
        selected = providers.get(override_id)
        if not selected:
            raise RuntimeError(f"Unknown provider override: {provider_override}")
        if resolved_privacy_class not in selected.get("allowed_privacy", []):
            raise RuntimeError(
                f"Provider {override_id} is not allowed for privacy class {resolved_privacy_class}"
            )
        if not selected.get("configured"):
            raise RuntimeError(f"Provider {override_id} is not configured")
        reason = "explicit provider override"
    elif resolved_privacy_class in {"private", "secret"}:
        selected = providers["frontier_gateway"]
        reason = f"{resolved_privacy_class} data stays on the frontier lane"
    elif resolved_task_class in FRONTIER_ONLY_TASKS:
        selected = providers["frontier_gateway"]
        reason = f"{resolved_task_class} tasks stay on the frontier lane"
    elif (
        resolved_privacy_class == "public"
        and config["allow_public_external"]
        and providers["public_openai"]["configured"]
        and resolved_task_class in PUBLIC_ELIGIBLE_TASKS
    ):
        selected = providers["public_openai"]
        reason = "public low-risk task routed to the public external lane"
    elif (
        resolved_privacy_class in providers["cheap_openai"]["allowed_privacy"]
        and providers["cheap_openai"]["configured"]
        and resolved_task_class in CHEAP_ELIGIBLE_TASKS
    ):
        selected = providers["cheap_openai"]
        reason = "low-cost compatible lane available for this task class"
    else:
        selected = providers["frontier_gateway"]
        reason = "defaulting to the frontier lane"

    return {
        "policy_version": config["policy_version"],
        "task_class": resolved_task_class,
        "privacy_class": resolved_privacy_class,
        "selected_provider": provider_public_view(selected),
        "reason": reason,
        "usage_ledger_file": config["usage_ledger_file"],
        "providers": [provider_public_view(provider) for provider in providers.values()],
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

    input_rate = provider.get("input_cost_per_million")
    output_rate = provider.get("output_cost_per_million")
    if input_rate is None and output_rate is None:
        return None

    input_cost = (usage.get("input_tokens", 0) / 1_000_000) * (input_rate or 0.0)
    output_cost = (usage.get("output_tokens", 0) / 1_000_000) * (output_rate or 0.0)
    return round(input_cost + output_cost, 8)


def append_usage_ledger(entry: dict[str, Any]) -> str:
    config = load_router_config()
    ledger_path = Path(config["usage_ledger_file"])
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"logged_at": utc_now(), **entry}
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return str(ledger_path)


def policy_command() -> int:
    print(json.dumps(public_policy_view(load_router_config()), indent=2, ensure_ascii=True))
    return 0


def providers_command() -> int:
    config = load_router_config()
    print(json.dumps([provider_public_view(provider) for provider in config["providers"].values()], indent=2, ensure_ascii=True))
    return 0


def plan_command(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            choose_provider(
                args.task,
                task_class=args.task_class,
                privacy_class=args.privacy_class,
                provider_override=args.provider,
            ),
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freewiller provider routing and usage ledger.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    policy_parser = subparsers.add_parser("policy")
    policy_parser.set_defaults(func=lambda _args: policy_command())

    providers_parser = subparsers.add_parser("providers")
    providers_parser.set_defaults(func=lambda _args: providers_command())

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--task", required=True)
    plan_parser.add_argument("--task-class", default="")
    plan_parser.add_argument("--privacy-class", default="")
    plan_parser.add_argument("--provider", default="")
    plan_parser.set_defaults(func=plan_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
