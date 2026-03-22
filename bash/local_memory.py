#!/usr/bin/env python3

import argparse
import json
import math
import os
import subprocess
import sys
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCAL_LLM_DIR = Path(os.environ.get("LOCAL_LLM_DIR", "/var/lib/openclaw-local-llm"))
MEMORY_DIR = LOCAL_LLM_DIR / "memory"
MEMORY_DB = MEMORY_DIR / "entries.jsonl"
LOCAL_LLM_SH = Path("/local/bash/local_llm.sh")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_store() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DB.touch(exist_ok=True)


def read_entries() -> list[dict[str, Any]]:
    ensure_store()
    entries: list[dict[str, Any]] = []
    with MEMORY_DB.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def append_entry(entry: dict[str, Any]) -> None:
    ensure_store()
    with MEMORY_DB.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def call_local_llm(mode: str, text: str) -> str:
    result = subprocess.run(
        [str(LOCAL_LLM_SH), mode, text],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_extract_output(output: str) -> dict[str, list[str]]:
    sections = {"FACTS": [], "TODO": [], "CONSTRAINTS": []}
    current = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line in sections:
            current = line
            continue
        if line.startswith("- ") and current:
            value = line[2:].strip()
            if value and value.lower() != "none":
                sections[current].append(value)

    return {
        "facts": sections["FACTS"],
        "todo": sections["TODO"],
        "constraints": sections["CONSTRAINTS"],
    }


def truncate_text(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def embed_text(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_API_URL}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["embedding"]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def next_id(entries: list[dict[str, Any]]) -> str:
    return f"mem-{len(entries) + 1:06d}"


def add_entry(args: argparse.Namespace) -> int:
    entries = read_entries()
    raw_text = args.text.strip()

    summary = call_local_llm("summarize", raw_text)
    if summary == "LOCAL_SUMMARY_UNAVAILABLE":
        summary = truncate_text(raw_text)

    extract_output = call_local_llm("extract", raw_text)
    extracted = parse_extract_output(extract_output)
    embedding = embed_text(summary)

    entry = {
      "id": next_id(entries),
      "created_at": utc_now(),
      "kind": args.kind,
      "source": args.source,
      "tags": [tag for tag in args.tags.split(",") if tag] if args.tags else [],
      "summary": summary,
      "text": raw_text,
      "facts": extracted["facts"],
      "todo": extracted["todo"],
      "constraints": extracted["constraints"],
      "embedding": embedding,
    }

    append_entry(entry)
    print(entry["id"])
    return 0


def search_entries(args: argparse.Namespace) -> int:
    entries = read_entries()
    if not entries:
        print("[]")
        return 0

    query_embedding = embed_text(args.query)
    scored = []
    for entry in entries:
        score = cosine_similarity(query_embedding, entry.get("embedding", []))
        scored.append({"score": score, "entry": entry})

    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[: args.limit]

    output = [
        {
            "score": round(item["score"], 4),
            "id": item["entry"]["id"],
            "kind": item["entry"]["kind"],
            "source": item["entry"]["source"],
            "summary": item["entry"]["summary"],
            "facts": item["entry"].get("facts", []),
            "todo": item["entry"].get("todo", []),
            "constraints": item["entry"].get("constraints", []),
            "tags": item["entry"].get("tags", []),
        }
        for item in top
    ]

    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def context_block(args: argparse.Namespace) -> int:
    entries = read_entries()
    if not entries:
      print("No memory entries found.")
      return 0

    query_embedding = embed_text(args.query)
    scored = []
    for entry in entries:
        score = cosine_similarity(query_embedding, entry.get("embedding", []))
        scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: args.limit]

    blocks = []
    for score, entry in top:
        facts = "\n".join(f"- {item}" for item in entry.get("facts", [])[:3]) or "- none"
        todo = "\n".join(f"- {item}" for item in entry.get("todo", [])[:3]) or "- none"
        constraints = "\n".join(f"- {item}" for item in entry.get("constraints", [])[:3]) or "- none"
        blocks.append(
            textwrap.dedent(
                f"""\
                [{entry['id']}] score={score:.4f} kind={entry['kind']} source={entry['source']}
                Summary: {entry['summary']}
                Facts:
                {facts}
                TODO:
                {todo}
                Constraints:
                {constraints}
                """
            ).strip()
        )

    print("\n\n".join(blocks))
    return 0


def list_entries(args: argparse.Namespace) -> int:
    entries = read_entries()
    recent = entries[-args.limit :]
    print(json.dumps(recent, indent=2, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local memory store for OpenClaw groundwork.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--kind", required=True)
    add_parser.add_argument("--source", required=True)
    add_parser.add_argument("--text", required=True)
    add_parser.add_argument("--tags", default="")
    add_parser.set_defaults(func=add_entry)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.set_defaults(func=search_entries)

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("--query", required=True)
    context_parser.add_argument("--limit", type=int, default=5)
    context_parser.set_defaults(func=context_block)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(func=list_entries)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
