#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


LOCAL_LLM_SH = Path("/local/bash/local_llm.sh")
LOCAL_MEMORY_PY = Path("/local/bash/local_memory.py")
LOCAL_LLM_DIR = Path(os.environ.get("LOCAL_LLM_DIR", "/var/lib/openclaw-local-llm"))
PACKAGES_DIR = LOCAL_LLM_DIR / "packages"


def ensure_dirs() -> None:
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)


def run_command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def route_task(task: str) -> dict[str, str]:
    output = run_command([str(LOCAL_LLM_SH), "route", task])
    label = "REMOTE"
    reason = "No reason returned."
    for line in output.splitlines():
        if line.startswith("LABEL:"):
            label = line.split(":", 1)[1].strip()
        elif line.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
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


def save_package(content: str, prefix: str = "remote-package") -> str:
    ensure_dirs()
    existing = sorted(PACKAGES_DIR.glob(f"{prefix}-*.md"))
    next_index = len(existing) + 1
    output_path = PACKAGES_DIR / f"{prefix}-{next_index:06d}.md"
    output_path.write_text(content + "\n", encoding="utf-8")
    return str(output_path)


def orchestrate(args: argparse.Namespace) -> int:
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

    output = {
        "route": route,
        "stored_memory_id": memory_id,
        "remote_package_path": package_path,
        "memory_hits": search_memory(args.task, args.limit),
        "local_summary": local_summary,
        "local_extract": local_extract,
    }
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local orchestration layer for routing, memory, and remote prompt packaging.")
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
