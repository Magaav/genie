#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path
from typing import Any


LOCAL_LLM_SH = Path("/local/bash/local_llm.sh")
LOCAL_MEMORY_PY = Path("/local/bash/local_memory.py")
PRIMARY_GATEWAY_ENV_BASENAME = "freewiller-gateway.env"
LEGACY_GATEWAY_ENV_BASENAME = "openclaw-gateway.env"


def resolve_state_dir() -> Path:
    if os.environ.get("LOCAL_LLM_DIR"):
        return Path(os.environ["LOCAL_LLM_DIR"])
    default_path = Path("/var/lib/freewiller")
    legacy_path = Path("/var/lib/openclaw-local-llm")
    if default_path.exists():
        return default_path
    if legacy_path.exists():
        return legacy_path
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
        "MODEL": os.environ.get("FREEWILLER_MODEL", os.environ.get("OPENCLAW_MODEL", "freewiller")),
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
    return run_command(
        [
            "python3",
            str(LOCAL_MEMORY_PY),
            "add",
            "--kind",
            kind,
            "--source",
            source,
            "--text",
            text,
            "--tags",
            tags,
        ]
    )


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


def dispatch_to_gateway(package_path: str, instructions: str | None = None) -> dict[str, Any]:
    config = load_gateway_config()
    gateway_url = config.get("GATEWAY_URL", "").rstrip("/")
    gateway_token = config.get("GATEWAY_TOKEN", "")
    if not gateway_url or not gateway_token:
        raise RuntimeError(
            f"Gateway config is incomplete. Set FREEWILLER_GATEWAY_URL and FREEWILLER_GATEWAY_TOKEN in {PRIMARY_GATEWAY_ENV_FILE}."
        )

    package_content = Path(package_path).read_text(encoding="utf-8")
    body: dict[str, Any] = {
        "model": config.get("MODEL", "freewiller"),
        "input": package_content,
        "user": config.get("USER", "freewiller-local-agent"),
        "max_output_tokens": int(config.get("MAX_OUTPUT_TOKENS", "2048")),
        "stream": False,
    }
    if instructions:
        body["instructions"] = instructions

    req = urllib.request.Request(
        f"{gateway_url}/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": config.get("AGENT_ID", "main"),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        response_json = json.loads(response.read().decode("utf-8"))

    text_output = extract_response_text(response_json)
    raw_json_path = save_response(json.dumps(response_json, indent=2, ensure_ascii=True) + "\n", "freewiller-gateway-response", "json")
    text_path = save_response(text_output + ("\n" if text_output else ""), "freewiller-gateway-response", "md")

    return {
        "response_json": response_json,
        "response_text": text_output,
        "response_json_path": raw_json_path,
        "response_text_path": text_path,
    }


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
    gateway_result = dispatch_to_gateway(
        output["remote_package_path"],
        instructions=default_gateway_instructions(),
    )
    output["gateway_response_text"] = gateway_result["response_text"]
    output["gateway_response_json_path"] = gateway_result["response_json_path"]
    output["gateway_response_text_path"] = gateway_result["response_text_path"]
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
    orchestrate_parser.set_defaults(func=orchestrate)

    dispatch_parser = subparsers.add_parser("dispatch")
    dispatch_parser.add_argument("--task", required=True)
    dispatch_parser.add_argument("--limit", type=int, default=3)
    dispatch_parser.add_argument("--store", action="store_true")
    dispatch_parser.add_argument("--kind", default="note")
    dispatch_parser.add_argument("--source", default="session")
    dispatch_parser.add_argument("--tags", default="local,agent")
    dispatch_parser.add_argument("--memory-text", default="")
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
