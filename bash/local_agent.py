#!/usr/bin/env python3

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import provider_router

LOCAL_LLM_SH = Path("/local/bash/local_llm.sh")
LOCAL_MEMORY_PY = Path("/local/bash/local_memory.py")
PRIMARY_GATEWAY_ENV_BASENAME = "freewiller-gateway.env"
LEGACY_GATEWAY_ENV_BASENAME = "openclaw-gateway.env"


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
PACKAGES_DIR = LOCAL_LLM_DIR / "packages"
RESPONSES_DIR = LOCAL_LLM_DIR / "responses"
PRIMARY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / PRIMARY_GATEWAY_ENV_BASENAME
LEGACY_GATEWAY_ENV_FILE = LOCAL_LLM_DIR / LEGACY_GATEWAY_ENV_BASENAME


def ensure_dirs() -> None:
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)


def load_gateway_config() -> dict[str, str]:
    config = {
        "GATEWAY_URL": os.environ.get("FREEWILLER_GATEWAY_URL", os.environ.get("OPENCLAW_GATEWAY_URL", "")),
        "GATEWAY_TOKEN": os.environ.get("FREEWILLER_GATEWAY_TOKEN", os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")),
        "AGENT_ID": os.environ.get("FREEWILLER_AGENT_ID", os.environ.get("OPENCLAW_AGENT_ID", "main")),
        "MODEL": os.environ.get("FREEWILLER_MODEL", os.environ.get("OPENCLAW_MODEL", "openclaw:main")),
        "GATEWAY_API": os.environ.get("FREEWILLER_GATEWAY_API", os.environ.get("OPENCLAW_GATEWAY_API", "auto")),
        "USER": os.environ.get("FREEWILLER_USER", os.environ.get("OPENCLAW_USER", "freewiller-local-agent")),
        "MAX_OUTPUT_TOKENS": os.environ.get(
            "FREEWILLER_MAX_OUTPUT_TOKENS",
            os.environ.get("OPENCLAW_MAX_OUTPUT_TOKENS", "2048"),
        ),
    }

    for env_file in (PRIMARY_GATEWAY_ENV_FILE, LEGACY_GATEWAY_ENV_FILE):
        if not env_file.exists():
            continue

        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key in {"FREEWILLER_GATEWAY_URL", "OPENCLAW_GATEWAY_URL"}:
                config["GATEWAY_URL"] = value
            elif key in {"FREEWILLER_GATEWAY_TOKEN", "OPENCLAW_GATEWAY_TOKEN"}:
                config["GATEWAY_TOKEN"] = value
            elif key in {"FREEWILLER_AGENT_ID", "OPENCLAW_AGENT_ID"}:
                config["AGENT_ID"] = value
            elif key in {"FREEWILLER_MODEL", "OPENCLAW_MODEL"}:
                config["MODEL"] = value
            elif key in {"FREEWILLER_GATEWAY_API", "OPENCLAW_GATEWAY_API"}:
                config["GATEWAY_API"] = value
            elif key in {"FREEWILLER_USER", "OPENCLAW_USER"}:
                config["USER"] = value
            elif key in {"FREEWILLER_MAX_OUTPUT_TOKENS", "OPENCLAW_MAX_OUTPUT_TOKENS"}:
                config["MAX_OUTPUT_TOKENS"] = value

    return config


def run_command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def route_task(task: str) -> dict[str, str]:
    output = run_command([str(LOCAL_LLM_SH), "route", task])
    label = "REMOTE"
    reason = "No reason returned."
    for line in output.splitlines():
        if line.startswith("LABEL:"):
            label = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip().strip('"')
    return {"label": label, "reason": reason, "raw": output}


def summarize_text(text: str) -> str:
    return run_command([str(LOCAL_LLM_SH), "summarize", text])


def extract_text(text: str) -> str:
    return run_command([str(LOCAL_LLM_SH), "extract", text])


def add_memory(kind: str, source: str, text: str, tags: str) -> str:
    output = run_command(
        [
            "python3",
            str(LOCAL_MEMORY_PY),
            "ingest",
            "--channel",
            "local-agent",
            "--session-id",
            "orchestrate",
            "--role",
            "user",
            "--source",
            source,
            "--kind",
            kind,
            "--text",
            text,
            "--tags",
            tags,
        ]
    )
    payload = json.loads(output)
    return payload.get("memory_id", "")


def retrieve_context(query: str, limit: int) -> str:
    return run_command(
        [
            "python3",
            str(LOCAL_MEMORY_PY),
            "context",
            "--query",
            query,
            "--limit",
            str(limit),
        ]
    )


def search_memory(query: str, limit: int) -> list[dict[str, Any]]:
    output = run_command(
        [
            "python3",
            str(LOCAL_MEMORY_PY),
            "search",
            "--query",
            query,
            "--limit",
            str(limit),
        ]
    )
    return json.loads(output)


def build_remote_package(
    task: str,
    route: dict[str, str],
    local_summary: str,
    local_extract: str,
    memory_context: str,
) -> str:
    return textwrap.dedent(
        f"""\
        TASK:
        {task}

        ROUTE:
        LABEL: {route['label']}
        REASON: {route['reason']}

        LOCAL_SUMMARY:
        {local_summary}

        LOCAL_EXTRACT:
        {local_extract}

        RETRIEVED_MEMORY:
        {memory_context if memory_context else 'No memory entries found.'}
        """
    ).strip()


def save_package(content: str, prefix: str = "freewiller-remote-package") -> str:
    ensure_dirs()
    existing = sorted(PACKAGES_DIR.glob(f"{prefix}-*.md"))
    next_index = len(existing) + 1
    output_path = PACKAGES_DIR / f"{prefix}-{next_index:06d}.md"
    output_path.write_text(content + "\n", encoding="utf-8")
    return str(output_path)


def save_response(content: str, prefix: str, suffix: str) -> str:
    ensure_dirs()
    existing = sorted(RESPONSES_DIR.glob(f"{prefix}-*.{suffix}"))
    next_index = len(existing) + 1
    output_path = RESPONSES_DIR / f"{prefix}-{next_index:06d}.{suffix}"
    output_path.write_text(content, encoding="utf-8")
    return str(output_path)


def extract_response_text(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]

    output_items = response_json.get("output", [])
    chunks: list[str] = []
    for item in output_items:
        for content in item.get("content", []):
            text_value = content.get("text") or content.get("output_text")
            if text_value:
                chunks.append(text_value)
    return "\n".join(chunks).strip()


def extract_chat_completions_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    chunks.append(text_value)
        return "\n".join(chunks).strip()

    return ""


def extract_usage(response_json: dict[str, Any]) -> dict[str, int]:
    usage = response_json.get("usage")
    if isinstance(usage, dict):
        return provider_router.normalize_usage(usage)

    nested_usage = (
        response_json.get("result", {})
        .get("meta", {})
        .get("agentMeta", {})
        .get("usage", {})
    )
    if isinstance(nested_usage, dict):
        return provider_router.normalize_usage(nested_usage)

    return provider_router.normalize_usage({})


def response_prefix_for_provider(provider_id: str) -> str:
    safe_id = provider_router.sanitize_provider_name(provider_id) or "provider"
    return f"freewiller-{safe_id}-response"


def wait_for_gateway_live(gateway_url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    health_url = f"{gateway_url.rstrip('/')}/healthz"
    last_error = ""

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, http.client.RemoteDisconnected) as exc:
            last_error = str(exc)
        time.sleep(1)

    if last_error:
        raise RuntimeError(f"Gateway did not become live at {health_url}: {last_error}")
    raise RuntimeError(f"Gateway did not become live at {health_url}")


def build_gateway_candidates(
    config: dict[str, str],
    package_content: str,
    instructions: str | None,
) -> list[tuple[str, dict[str, Any], Any]]:
    model = config.get("MODEL", "openclaw:main")
    user = config.get("USER", "freewiller-local-agent")
    max_output_tokens = int(config.get("MAX_OUTPUT_TOKENS", "2048"))
    requested_api = config.get("GATEWAY_API", "auto").strip().lower()

    responses_body: dict[str, Any] = {
        "model": model,
        "input": package_content,
        "user": user,
        "max_output_tokens": max_output_tokens,
        "stream": False,
    }
    if instructions:
        responses_body["instructions"] = instructions

    chat_messages: list[dict[str, str]] = []
    if instructions:
        chat_messages.append({"role": "system", "content": instructions})
    chat_messages.append({"role": "user", "content": package_content})
    chat_body: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "user": user,
        "max_tokens": max_output_tokens,
        "stream": False,
    }

    if requested_api in {"responses", "openresponses"}:
        return [("/v1/responses", responses_body, extract_response_text)]
    if requested_api in {"chat", "chat_completions", "chat-completions"}:
        return [("/v1/chat/completions", chat_body, extract_chat_completions_text)]

    return [
        ("/v1/responses", responses_body, extract_response_text),
        ("/v1/chat/completions", chat_body, extract_chat_completions_text),
    ]


def extract_http_error_message(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    if not body:
        return f"HTTP {exc.code} {exc.reason}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return f"HTTP {exc.code} {exc.reason}: {body.strip()}"

    if isinstance(payload, dict):
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            error_message = error_obj.get("message")
            if isinstance(error_message, str) and error_message.strip():
                return f"HTTP {exc.code} {exc.reason}: {error_message.strip()}"
    return f"HTTP {exc.code} {exc.reason}: {body.strip()}"


def dispatch_to_gateway(
    package_path: str,
    instructions: str | None = None,
    *,
    provider_id: str = "frontier_gateway",
) -> dict[str, Any]:
    config = load_gateway_config()
    gateway_url = config.get("GATEWAY_URL", "").rstrip("/")
    gateway_token = config.get("GATEWAY_TOKEN", "")
    if not gateway_url or not gateway_token:
        raise RuntimeError(
            f"Gateway config is incomplete. Set FREEWILLER_GATEWAY_URL and FREEWILLER_GATEWAY_TOKEN in {PRIMARY_GATEWAY_ENV_FILE}."
        )

    package_content = Path(package_path).read_text(encoding="utf-8")
    wait_for_gateway_live(gateway_url)
    headers = {
        "Authorization": f"Bearer {gateway_token}",
        "Content-Type": "application/json",
        "x-openclaw-agent-id": config.get("AGENT_ID", "main"),
    }
    candidates = build_gateway_candidates(config, package_content, instructions)
    response_json: dict[str, Any] | None = None
    text_output = ""
    last_error = "Gateway request failed."

    for attempt in range(1, 4):
        for index, (endpoint, body, extract_text_fn) in enumerate(candidates):
            req = urllib.request.Request(
                f"{gateway_url}{endpoint}",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as response:
                    response_json = json.loads(response.read().decode("utf-8"))
                text_output = extract_text_fn(response_json)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and index < len(candidates) - 1:
                    last_error = extract_http_error_message(exc)
                    continue
                raise RuntimeError(extract_http_error_message(exc)) from exc
            except (
                urllib.error.URLError,
                http.client.RemoteDisconnected,
                ConnectionResetError,
                TimeoutError,
                socket.timeout,
            ) as exc:
                last_error = str(exc)
                if attempt >= 3:
                    raise RuntimeError(f"Gateway request failed after retries: {last_error}") from exc
                time.sleep(attempt)
                break

        if response_json is not None:
            break
    else:
        raise RuntimeError(last_error)

    if response_json is None:
        raise RuntimeError(last_error)

    response_prefix = response_prefix_for_provider(provider_id)
    raw_json_path = save_response(json.dumps(response_json, indent=2, ensure_ascii=True) + "\n", response_prefix, "json")
    text_path = save_response(text_output + ("\n" if text_output else ""), response_prefix, "md")

    return {
        "response_json": response_json,
        "response_text": text_output,
        "response_json_path": raw_json_path,
        "response_text_path": text_path,
        "usage": extract_usage(response_json),
    }


def build_openai_compatible_candidates(
    provider: dict[str, Any],
    package_content: str,
    instructions: str | None,
) -> list[tuple[str, dict[str, Any], Any]]:
    api_mode = provider.get("api_mode", "chat").strip().lower()
    model = provider.get("model", "")
    max_output_tokens = int(provider.get("max_output_tokens", 1024))
    user = load_gateway_config().get("USER", "freewiller-local-agent")

    responses_body: dict[str, Any] = {
        "model": model,
        "input": package_content,
        "user": user,
        "max_output_tokens": max_output_tokens,
        "stream": False,
    }
    if instructions:
        responses_body["instructions"] = instructions

    messages: list[dict[str, str]] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    messages.append({"role": "user", "content": package_content})
    chat_body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "user": user,
        "max_tokens": max_output_tokens,
        "stream": False,
    }

    if api_mode == "responses":
        return [("/responses", responses_body, extract_response_text)]
    if api_mode in {"chat", "chat_completions", "chat-completions"}:
        return [("/chat/completions", chat_body, extract_chat_completions_text)]

    return [
        ("/responses", responses_body, extract_response_text),
        ("/chat/completions", chat_body, extract_chat_completions_text),
    ]


def dispatch_to_openai_compatible(
    provider: dict[str, Any],
    package_path: str,
    instructions: str | None = None,
) -> dict[str, Any]:
    api_base_url = str(provider.get("api_base_url", "")).rstrip("/")
    api_key = str(provider.get("api_key", ""))
    model = str(provider.get("model", ""))
    if not api_base_url or not api_key or not model:
        raise RuntimeError(f"Provider {provider.get('id', 'unknown')} is not configured")

    package_content = Path(package_path).read_text(encoding="utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    candidates = build_openai_compatible_candidates(provider, package_content, instructions)
    response_json: dict[str, Any] | None = None
    text_output = ""
    last_error = "Provider request failed."

    for endpoint, body, extract_text_fn in candidates:
        req = urllib.request.Request(
            f"{api_base_url}{endpoint}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            text_output = extract_text_fn(response_json)
            break
        except urllib.error.HTTPError as exc:
            last_error = extract_http_error_message(exc)
            if exc.code == 404 and endpoint == "/responses":
                continue
            raise RuntimeError(last_error) from exc
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            ConnectionResetError,
            TimeoutError,
            socket.timeout,
        ) as exc:
            raise RuntimeError(f"Provider request failed: {exc}") from exc

    if response_json is None:
        raise RuntimeError(last_error)

    response_prefix = response_prefix_for_provider(str(provider.get("id", "provider")))
    raw_json_path = save_response(json.dumps(response_json, indent=2, ensure_ascii=True) + "\n", response_prefix, "json")
    text_path = save_response(text_output + ("\n" if text_output else ""), response_prefix, "md")

    return {
        "response_json": response_json,
        "response_text": text_output,
        "response_json_path": raw_json_path,
        "response_text_path": text_path,
        "usage": extract_usage(response_json),
    }


def dispatch_to_provider(
    package_path: str,
    *,
    instructions: str | None,
    provider_plan: dict[str, Any],
) -> dict[str, Any]:
    provider = provider_plan["selected_provider"]
    provider_id = provider["id"]
    provider_kind = provider["kind"]
    started_at = time.time()
    package_chars = len(Path(package_path).read_text(encoding="utf-8"))

    try:
        if provider_kind == "gateway":
            result = dispatch_to_gateway(package_path, instructions=instructions, provider_id=provider_id)
        elif provider_kind == "openai_compatible":
            full_provider = provider_router.load_router_config()["providers"][provider_id]
            result = dispatch_to_openai_compatible(full_provider, package_path, instructions=instructions)
        else:
            raise RuntimeError(f"Unsupported provider kind: {provider_kind}")

        latency_ms = int((time.time() - started_at) * 1000)
        usage = provider_router.normalize_usage(result.get("usage", {}))
        estimated_cost_usd = provider_router.estimate_cost_usd(provider_id, usage)
        usage_log_path = provider_router.append_usage_ledger(
            {
                "provider_id": provider_id,
                "provider_kind": provider_kind,
                "provider_model": provider.get("model", ""),
                "task_class": provider_plan["task_class"],
                "privacy_class": provider_plan["privacy_class"],
                "status": "ok",
                "latency_ms": latency_ms,
                "package_path": package_path,
                "package_chars": package_chars,
                "response_json_path": result["response_json_path"],
                "response_text_path": result["response_text_path"],
                "usage": usage,
                "estimated_cost_usd": estimated_cost_usd,
            }
        )
        result["usage"] = usage
        result["estimated_cost_usd"] = estimated_cost_usd
        result["usage_log_path"] = usage_log_path
        return result
    except Exception as exc:
        latency_ms = int((time.time() - started_at) * 1000)
        usage_log_path = provider_router.append_usage_ledger(
            {
                "provider_id": provider_id,
                "provider_kind": provider_kind,
                "provider_model": provider.get("model", ""),
                "task_class": provider_plan["task_class"],
                "privacy_class": provider_plan["privacy_class"],
                "status": "error",
                "latency_ms": latency_ms,
                "package_path": package_path,
                "package_chars": package_chars,
                "error": str(exc),
            }
        )
        raise RuntimeError(f"{exc} (logged to {usage_log_path})") from exc


def default_gateway_instructions() -> str:
    return textwrap.dedent(
        """\
        You are receiving a packaged request from the Freewiller local orchestration layer.
        Treat ROUTE, LOCAL_SUMMARY, LOCAL_EXTRACT, and RETRIEVED_MEMORY as prep material.
        Focus on answering the TASK directly.
        """
    ).strip()


def execute_orchestration(args: argparse.Namespace) -> dict[str, Any]:
    route = route_task(args.task)
    memory_context = retrieve_context(args.task, args.limit)
    provider_plan = provider_router.choose_provider(
        args.task,
        task_class=getattr(args, "task_class", ""),
        privacy_class=getattr(args, "privacy_class", ""),
        provider_override=getattr(args, "provider", ""),
    )

    local_summary = "SKIPPED_LOCAL_SUMMARY"
    local_extract = "SKIPPED_LOCAL_EXTRACT"

    if route["label"] == "LOCAL":
        local_summary = summarize_text(args.task)
        local_extract = extract_text(args.task)

    if args.store:
        memory_source_text = args.memory_text if args.memory_text else args.task
        memory_id = add_memory(args.kind, args.source, memory_source_text, args.tags)
    else:
        memory_id = ""

    remote_package = build_remote_package(
        task=args.task,
        route=route,
        local_summary=local_summary,
        local_extract=local_extract,
        memory_context=memory_context,
    )
    package_path = save_package(remote_package)

    return {
        "route": route,
        "provider_plan": provider_plan,
        "stored_memory_id": memory_id,
        "remote_package_path": package_path,
        "memory_hits": search_memory(args.task, args.limit),
        "local_summary": local_summary,
        "local_extract": local_extract,
    }


def orchestrate(args: argparse.Namespace) -> int:
    output = execute_orchestration(args)
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def dispatch(args: argparse.Namespace) -> int:
    output = execute_orchestration(args)
    provider_result = dispatch_to_provider(
        output["remote_package_path"],
        instructions=default_gateway_instructions(),
        provider_plan=output["provider_plan"],
    )
    output["provider_response_text"] = provider_result["response_text"]
    output["provider_response_json_path"] = provider_result["response_json_path"]
    output["provider_response_text_path"] = provider_result["response_text_path"]
    output["gateway_response_text"] = provider_result["response_text"]
    output["gateway_response_json_path"] = provider_result["response_json_path"]
    output["gateway_response_text_path"] = provider_result["response_text_path"]
    output["usage"] = provider_result["usage"]
    output["estimated_cost_usd"] = provider_result["estimated_cost_usd"]
    output["usage_log_path"] = provider_result["usage_log_path"]
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freewiller orchestration layer for routing, memory, and remote prompt packaging.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    orchestrate_parser = subparsers.add_parser("orchestrate")
    orchestrate_parser.add_argument("--task", required=True)
    orchestrate_parser.add_argument("--limit", type=int, default=3)
    orchestrate_parser.add_argument("--store", action="store_true")
    orchestrate_parser.add_argument("--kind", default="note")
    orchestrate_parser.add_argument("--source", default="session")
    orchestrate_parser.add_argument("--tags", default="local,agent")
    orchestrate_parser.add_argument("--memory-text", default="")
    orchestrate_parser.add_argument("--task-class", default="")
    orchestrate_parser.add_argument("--privacy-class", default="")
    orchestrate_parser.add_argument("--provider", default="")
    orchestrate_parser.set_defaults(func=orchestrate)

    dispatch_parser = subparsers.add_parser("dispatch")
    dispatch_parser.add_argument("--task", required=True)
    dispatch_parser.add_argument("--limit", type=int, default=3)
    dispatch_parser.add_argument("--store", action="store_true")
    dispatch_parser.add_argument("--kind", default="note")
    dispatch_parser.add_argument("--source", default="session")
    dispatch_parser.add_argument("--tags", default="local,agent")
    dispatch_parser.add_argument("--memory-text", default="")
    dispatch_parser.add_argument("--task-class", default="")
    dispatch_parser.add_argument("--privacy-class", default="")
    dispatch_parser.add_argument("--provider", default="")
    dispatch_parser.set_defaults(func=dispatch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
