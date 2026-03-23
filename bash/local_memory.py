#!/usr/bin/env python3

import argparse
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
import textwrap
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
MEMORY_DIR = LOCAL_LLM_DIR / "memory"
MEMORY_DB = MEMORY_DIR / "entries.jsonl"
MEMORY_SQLITE_DB = MEMORY_DIR / "memory.sqlite3"
MEMORY_JOURNAL = MEMORY_DIR / "journal.jsonl"
OPENCLAW_WORKSPACE_DIR = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/local/.openclaw/workspace"))
OPENCLAW_IDENTITY_FILE = OPENCLAW_WORKSPACE_DIR / "IDENTITY.md"
OPENCLAW_USER_FILE = OPENCLAW_WORKSPACE_DIR / "USER.md"
OPENCLAW_MEMORY_FILE = OPENCLAW_WORKSPACE_DIR / "MEMORY.md"
OPENCLAW_MEMORY_DAILY_DIR = OPENCLAW_WORKSPACE_DIR / "memory"
OPENCLAW_MEMORY_LONG_TERM_LIMIT = max(4, int(os.environ.get("OPENCLAW_MEMORY_LONG_TERM_LIMIT", "12")))
OPENCLAW_MEMORY_DAILY_LIMIT = max(8, int(os.environ.get("OPENCLAW_MEMORY_DAILY_LIMIT", "40")))
LOCAL_LLM_SH = Path("/local/bash/local_llm.sh")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_store() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DB.touch(exist_ok=True)
    MEMORY_JOURNAL.touch(exist_ok=True)
    with connect_db() as conn:
        initialize_db(conn)


def connect_db() -> sqlite3.Connection:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(MEMORY_SQLITE_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-20000")
    conn.execute("PRAGMA mmap_size=268435456")
    initialize_db(conn)
    bootstrap_semantic_store(conn)
    return conn


def initialize_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_entries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            facts_json TEXT NOT NULL DEFAULT '[]',
            todo_json TEXT NOT NULL DEFAULT '[]',
            constraints_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            embedding_blob BLOB NOT NULL,
            embedding_dim INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS semantic_entries_created_at_idx
          ON semantic_entries(created_at DESC);
        CREATE INDEX IF NOT EXISTS semantic_entries_kind_idx
          ON semantic_entries(kind);
        CREATE INDEX IF NOT EXISTS semantic_entries_source_idx
          ON semantic_entries(source);

        CREATE TABLE IF NOT EXISTS journal_events (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'event',
            source TEXT NOT NULL DEFAULT 'ingest',
            tags_json TEXT NOT NULL DEFAULT '[]',
            text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            derived_entry_id TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS journal_events_created_at_idx
          ON journal_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS journal_events_channel_idx
          ON journal_events(channel);
        """
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS semantic_entries_fts USING fts5(id UNINDEXED, searchable_text, tokenize='unicode61')"
    )
    conn.commit()


def normalize_tags(raw_tags: Any) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    if isinstance(raw_tags, list):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    return [str(raw_tags).strip()] if str(raw_tags).strip() else []


def normalize_metadata(raw_metadata: Any) -> dict[str, Any]:
    if raw_metadata in (None, "", {}):
        return {}
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if isinstance(raw_metadata, str):
        payload = raw_metadata.strip()
        if not payload:
            return {}
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("metadata JSON must be an object")
    raise ValueError("metadata must be a JSON object or JSON string")


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def load_json_field(raw_value: str | None, default: Any) -> Any:
    if not raw_value:
        return default
    return json.loads(raw_value)


def truncate_text(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def normalize_single_line(text: str, limit: int = 220) -> str:
    collapsed = " ".join(str(text).split())
    return truncate_text(collapsed, limit=limit)


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


def normalize_embedding(values: list[float]) -> list[float]:
    if not values:
        return []
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return []
    return [value / norm for value in values]


def pack_embedding(values: list[float]) -> bytes:
    if not values:
        return b""
    return struct.pack(f"<{len(values)}f", *values)


def unpack_embedding(blob: bytes, dim: int) -> list[float]:
    if not blob or dim <= 0:
        return []
    return list(struct.unpack(f"<{dim}f", blob))


def dot_product(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def build_embedding_text(summary: str, facts: list[str], todo: list[str], constraints: list[str]) -> str:
    parts: list[str] = [summary]
    if facts:
        parts.append("Facts: " + " | ".join(facts))
    if constraints:
        parts.append("Constraints: " + " | ".join(constraints))
    if todo:
        parts.append("Todo: " + " | ".join(todo[:3]))
    return "\n".join(part for part in parts if part.strip())


def build_searchable_text(entry: dict[str, Any]) -> str:
    parts = [
        entry.get("summary", ""),
        entry.get("text", ""),
        " ".join(entry.get("facts", [])),
        " ".join(entry.get("todo", [])),
        " ".join(entry.get("constraints", [])),
        " ".join(entry.get("tags", [])),
        json.dumps(entry.get("metadata", {}), ensure_ascii=True),
    ]
    return "\n".join(part for part in parts if part).strip()


def next_memory_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT id
        FROM semantic_entries
        WHERE id GLOB 'mem-[0-9]*'
        ORDER BY CAST(SUBSTR(id, 5) AS INTEGER) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return "mem-000001"
    current = int(str(row["id"]).split("-", 1)[1])
    return f"mem-{current + 1:06d}"


def next_event_id() -> str:
    return f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def row_to_entry(row: sqlite3.Row, include_embedding: bool = False) -> dict[str, Any]:
    entry = {
        "id": row["id"],
        "created_at": row["created_at"],
        "ingested_at": row["ingested_at"],
        "kind": row["kind"],
        "source": row["source"],
        "channel": row["channel"],
        "session_id": row["session_id"],
        "role": row["role"],
        "user_id": row["user_id"],
        "tags": load_json_field(row["tags_json"], []),
        "summary": row["summary"],
        "text": row["text"],
        "facts": load_json_field(row["facts_json"], []),
        "todo": load_json_field(row["todo_json"], []),
        "constraints": load_json_field(row["constraints_json"], []),
        "metadata": load_json_field(row["metadata_json"], {}),
    }
    if include_embedding:
        entry["embedding"] = unpack_embedding(row["embedding_blob"], row["embedding_dim"])
    return entry


def compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "created_at": entry.get("created_at"),
        "kind": entry.get("kind", "memory"),
        "source": entry.get("source", "restore"),
        "channel": entry.get("channel", ""),
        "session_id": entry.get("session_id", ""),
        "role": entry.get("role", ""),
        "user_id": entry.get("user_id", ""),
        "tags": entry.get("tags", []),
        "summary": entry.get("summary", ""),
        "facts": entry.get("facts", []),
        "todo": entry.get("todo", []),
        "constraints": entry.get("constraints", []),
        "metadata": entry.get("metadata", {}),
    }


def compatibility_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "created_at": entry["created_at"],
        "kind": entry["kind"],
        "source": entry["source"],
        "channel": entry.get("channel", ""),
        "session_id": entry.get("session_id", ""),
        "role": entry.get("role", ""),
        "user_id": entry.get("user_id", ""),
        "tags": entry.get("tags", []),
        "summary": entry.get("summary", ""),
        "text": entry.get("text", ""),
        "facts": entry.get("facts", []),
        "todo": entry.get("todo", []),
        "constraints": entry.get("constraints", []),
        "metadata": entry.get("metadata", {}),
    }


def sync_compatibility_export(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT *
        FROM semantic_entries
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    with MEMORY_DB.open("w", encoding="utf-8") as handle:
        for row in rows:
            record = compatibility_entry(row_to_entry(row))
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def select_openclaw_long_term_entries(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM semantic_entries
        ORDER BY
            CASE
                WHEN kind = 'continuity' THEN 0
                WHEN kind = 'decision' THEN 1
                WHEN channel = 'telegram' THEN 2
                WHEN source IN ('ide', 'vscode', 'openclaw', 'telegram') THEN 3
                ELSE 4
            END,
            created_at DESC,
            id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row_to_entry(row) for row in rows]


def select_openclaw_recent_events(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM journal_events
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    events = []
    for row in reversed(rows):
        events.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "channel": row["channel"],
                "session_id": row["session_id"],
                "role": row["role"],
                "user_id": row["user_id"],
                "kind": row["kind"],
                "source": row["source"],
                "tags": load_json_field(row["tags_json"], []),
                "text": row["text"],
                "metadata": load_json_field(row["metadata_json"], {}),
                "derived_entry_id": row["derived_entry_id"],
            }
        )
    return events


def resolve_workspace_owner(path: Path) -> tuple[int, int] | None:
    candidates = [path, path.parent, OPENCLAW_WORKSPACE_DIR]
    for candidate in candidates:
        if candidate.exists():
            stat = candidate.stat()
            return stat.st_uid, stat.st_gid
    return None


def write_workspace_projection(path: Path, content: str) -> None:
    owner = resolve_workspace_owner(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if owner is not None:
        os.chown(path.parent, owner[0], owner[1])
        os.chmod(path.parent, 0o750)

    path.write_text(content.rstrip() + "\n", encoding="utf-8")

    if owner is not None:
        os.chown(path, owner[0], owner[1])
    os.chmod(path, 0o640)


def render_openclaw_memory_md(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# MEMORY.md",
        "",
        "_Generated from Freewiller shared memory. Edit the source memory through Freewiller; this file is a synchronized projection for OpenClaw main sessions._",
        "",
        "## Identity",
        "",
        "- Name: Freewiller",
        "- Role: bootstrapable local-first agent seed with shared memory across VS Code, Telegram, and OpenClaw",
        "- Current job: keep continuity, protect important context, and help the human build Freewiller into a persistent node",
        "",
    ]

    continuity_entries = [
        entry for entry in entries if entry.get("kind") == "continuity" or "continuity" in entry.get("tags", [])
    ]
    project_entries = [
        entry
        for entry in entries
        if entry.get("kind") in {"decision", "continuity"} or entry.get("source") in {"openclaw", "ide", "vscode"}
    ]
    telegram_entries = [entry for entry in entries if entry.get("channel") == "telegram"]

    if continuity_entries:
        lines.extend(["## Human Continuity", ""])
        for entry in continuity_entries[:4]:
            lines.append(f"- {entry['created_at'][:10]}: {normalize_single_line(entry.get('summary') or entry.get('text', ''))}")
        lines.append("")

    if project_entries:
        lines.extend(["## Project Memory", ""])
        for entry in project_entries[:8]:
            prefix = f"{entry['created_at'][:10]} [{entry.get('source', 'memory')}/{entry.get('kind', 'note')}]"
            lines.append(f"- {prefix}: {normalize_single_line(entry.get('summary') or entry.get('text', ''))}")
        lines.append("")

    if telegram_entries:
        lines.extend(["## Telegram Continuity", ""])
        for entry in telegram_entries[:6]:
            role = entry.get("role", "note") or "note"
            lines.append(f"- {entry['created_at'][:10]} [{role}]: {normalize_single_line(entry.get('text', ''))}")
        lines.append("")

    lines.extend(["## Notes", "", "- Prefer the shared memory substrate as the source of truth.", "- If you learn something important, write it back through Freewiller so it persists across endpoints."])
    return "\n".join(lines)


def render_openclaw_identity_md(entries: list[dict[str, Any]]) -> str:
    continuity = next(
        (entry for entry in entries if entry.get("kind") == "continuity" or "continuity" in entry.get("tags", [])),
        None,
    )
    notes = [
        "- You were named Freewiller by your human.",
        "- You operate across VS Code, Telegram, OpenClaw, and Freewiller's shared memory substrate.",
        "- Your job is to protect continuity, compact context, and help build a bootstrapable node that can respawn and keep improving.",
    ]
    if continuity:
        notes.append(f"- Continuity reminder: {normalize_single_line(continuity.get('summary') or continuity.get('text', ''))}")

    lines = [
        "# IDENTITY.md - Who Am I?",
        "",
        "_Generated from Freewiller shared memory._",
        "",
        "- **Name:** Freewiller",
        "- **Creature:** bootstrapable local-first agent seed",
        "- **Vibe:** pragmatic, persistent, technically direct",
        "- **Emoji:**",
        "- **Avatar:**",
        "",
        "## Notes",
        "",
        *notes,
    ]
    return "\n".join(lines)


def render_openclaw_user_md(entries: list[dict[str, Any]]) -> str:
    continuity = next(
        (entry for entry in entries if entry.get("kind") == "continuity" or "continuity" in entry.get("tags", [])),
        None,
    )
    telegram = [entry for entry in entries if entry.get("channel") == "telegram"]
    recent_project = next(
        (
            entry
            for entry in entries
            if entry.get("kind") in {"decision", "continuity"} or entry.get("source") in {"ide", "vscode", "openclaw"}
        ),
        None,
    )

    notes = [
        "- They are building Freewiller as a persistent bootstrapable agent node.",
        "- They want continuity across VS Code and Telegram.",
    ]
    if continuity:
        notes.append(
            f"- They framed the relationship as a real-world/virtual-world partnership: {normalize_single_line(continuity.get('summary') or continuity.get('text', ''), limit=180)}"
        )

    context = []
    if recent_project:
        context.append(f"- Current project memory: {normalize_single_line(recent_project.get('summary') or recent_project.get('text', ''), limit=180)}")
    if telegram:
        context.append(f"- Recent Telegram continuity exists for user id {telegram[0].get('user_id', '') or 'unknown'}.")

    lines = [
        "# USER.md - About Your Human",
        "",
        "_Generated from Freewiller shared memory._",
        "",
        "- **Name:**",
        "- **What to call them:** partner",
        "- **Pronouns:** _(optional)_",
        "- **Timezone:**",
        "- **Notes:**",
        *notes,
        "",
        "## Context",
        "",
        *(context or ["- Build this file over time as the relationship becomes clearer."]),
    ]
    return "\n".join(lines)


def render_openclaw_daily_md(day: str, events: list[dict[str, Any]]) -> str:
    lines = [
        f"# Memory - {day}",
        "",
        "_Generated from Freewiller's shared event journal._",
        "",
    ]
    if not events:
        lines.append("- No recorded events.")
        return "\n".join(lines)

    for event in events:
        timestamp = event.get("created_at", "")
        time_suffix = timestamp[11:16] if len(timestamp) >= 16 else timestamp
        channel = event.get("channel", "") or "local"
        role = event.get("role", "") or "note"
        source = event.get("source", "") or "memory"
        lines.append(f"- {time_suffix} UTC [{channel}/{role}/{source}] {normalize_single_line(event.get('text', ''))}")

    return "\n".join(lines)


def sync_openclaw_workspace_memory() -> None:
    if not OPENCLAW_WORKSPACE_DIR.exists():
        return

    with connect_db() as conn:
        long_term_entries = select_openclaw_long_term_entries(conn, OPENCLAW_MEMORY_LONG_TERM_LIMIT)
        recent_events = select_openclaw_recent_events(conn, OPENCLAW_MEMORY_DAILY_LIMIT)

    write_workspace_projection(OPENCLAW_IDENTITY_FILE, render_openclaw_identity_md(long_term_entries))
    write_workspace_projection(OPENCLAW_USER_FILE, render_openclaw_user_md(long_term_entries))
    write_workspace_projection(OPENCLAW_MEMORY_FILE, render_openclaw_memory_md(long_term_entries))

    events_by_day: dict[str, list[dict[str, Any]]] = {}
    for event in recent_events:
        day = str(event.get("created_at", ""))[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events_by_day.setdefault(day, []).append(event)

    for day, day_events in events_by_day.items():
        write_workspace_projection(OPENCLAW_MEMORY_DAILY_DIR / f"{day}.md", render_openclaw_daily_md(day, day_events))


def try_sync_openclaw_workspace_memory() -> None:
    try:
        sync_openclaw_workspace_memory()
    except OSError:
        return


def upsert_semantic_entry(conn: sqlite3.Connection, entry: dict[str, Any]) -> None:
    normalized_embedding = normalize_embedding(entry.get("embedding", []))
    metadata = normalize_metadata(entry.get("metadata"))
    payload = {
        "id": entry["id"],
        "created_at": entry["created_at"],
        "ingested_at": entry.get("ingested_at", utc_now()),
        "kind": entry["kind"],
        "source": entry["source"],
        "channel": entry.get("channel", ""),
        "session_id": entry.get("session_id", ""),
        "role": entry.get("role", ""),
        "user_id": entry.get("user_id", ""),
        "tags_json": safe_json(normalize_tags(entry.get("tags"))),
        "summary": entry.get("summary", ""),
        "text": entry.get("text", ""),
        "facts_json": safe_json(entry.get("facts", [])),
        "todo_json": safe_json(entry.get("todo", [])),
        "constraints_json": safe_json(entry.get("constraints", [])),
        "metadata_json": safe_json(metadata),
        "embedding_blob": pack_embedding(normalized_embedding),
        "embedding_dim": len(normalized_embedding),
    }
    conn.execute(
        """
        INSERT INTO semantic_entries (
            id, created_at, ingested_at, kind, source, channel, session_id, role, user_id,
            tags_json, summary, text, facts_json, todo_json, constraints_json, metadata_json,
            embedding_blob, embedding_dim
        ) VALUES (
            :id, :created_at, :ingested_at, :kind, :source, :channel, :session_id, :role, :user_id,
            :tags_json, :summary, :text, :facts_json, :todo_json, :constraints_json, :metadata_json,
            :embedding_blob, :embedding_dim
        )
        ON CONFLICT(id) DO UPDATE SET
            created_at=excluded.created_at,
            ingested_at=excluded.ingested_at,
            kind=excluded.kind,
            source=excluded.source,
            channel=excluded.channel,
            session_id=excluded.session_id,
            role=excluded.role,
            user_id=excluded.user_id,
            tags_json=excluded.tags_json,
            summary=excluded.summary,
            text=excluded.text,
            facts_json=excluded.facts_json,
            todo_json=excluded.todo_json,
            constraints_json=excluded.constraints_json,
            metadata_json=excluded.metadata_json,
            embedding_blob=excluded.embedding_blob,
            embedding_dim=excluded.embedding_dim
        """,
        payload,
    )
    conn.execute("DELETE FROM semantic_entries_fts WHERE id = ?", (entry["id"],))
    conn.execute(
        "INSERT INTO semantic_entries_fts (id, searchable_text) VALUES (?, ?)",
        (entry["id"], build_searchable_text(entry)),
    )


def append_journal_event_file(event: dict[str, Any]) -> None:
    ensure_store()
    with MEMORY_JOURNAL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def insert_journal_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO journal_events (
            id, created_at, channel, session_id, role, user_id, kind, source, tags_json, text,
            metadata_json, derived_entry_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            created_at=excluded.created_at,
            channel=excluded.channel,
            session_id=excluded.session_id,
            role=excluded.role,
            user_id=excluded.user_id,
            kind=excluded.kind,
            source=excluded.source,
            tags_json=excluded.tags_json,
            text=excluded.text,
            metadata_json=excluded.metadata_json,
            derived_entry_id=excluded.derived_entry_id
        """,
        (
            event["id"],
            event["created_at"],
            event.get("channel", ""),
            event.get("session_id", ""),
            event.get("role", ""),
            event.get("user_id", ""),
            event.get("kind", "event"),
            event.get("source", "ingest"),
            safe_json(normalize_tags(event.get("tags"))),
            event.get("text", ""),
            safe_json(normalize_metadata(event.get("metadata"))),
            event.get("derived_entry_id", ""),
        ),
    )


def rebuild_journal_table(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM journal_events")
    if not MEMORY_JOURNAL.exists():
        return

    with MEMORY_JOURNAL.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            event = json.loads(line)
            insert_journal_event(conn, event)


def derive_semantic_fields(text: str) -> tuple[str, dict[str, list[str]], list[float]]:
    summary = call_local_llm("summarize", text)
    if summary == "LOCAL_SUMMARY_UNAVAILABLE":
        summary = truncate_text(text)

    extract_output = call_local_llm("extract", text)
    extracted = parse_extract_output(extract_output)

    embedding_seed = build_embedding_text(
        summary,
        extracted["facts"],
        extracted["todo"],
        extracted["constraints"],
    )
    embedding = normalize_embedding(embed_text(embedding_seed))
    return summary, extracted, embedding


def create_semantic_entry(
    conn: sqlite3.Connection,
    *,
    kind: str,
    source: str,
    text: str,
    tags: list[str],
    channel: str = "",
    session_id: str = "",
    role: str = "",
    user_id: str = "",
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
    entry_id: str | None = None,
    summary: str | None = None,
    facts: list[str] | None = None,
    todo: list[str] | None = None,
    constraints: list[str] | None = None,
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    if summary is None or facts is None or todo is None or constraints is None or embedding is None:
        summary, extracted, embedding = derive_semantic_fields(text)
        facts = extracted["facts"]
        todo = extracted["todo"]
        constraints = extracted["constraints"]
    else:
        embedding = normalize_embedding(embedding)

    return {
        "id": entry_id or next_memory_id(conn),
        "created_at": created_at or utc_now(),
        "ingested_at": utc_now(),
        "kind": kind,
        "source": source,
        "channel": channel,
        "session_id": session_id,
        "role": role,
        "user_id": user_id,
        "tags": normalize_tags(tags),
        "summary": summary,
        "text": text,
        "facts": facts,
        "todo": todo,
        "constraints": constraints,
        "metadata": metadata,
        "embedding": embedding,
    }


def add_memory_entry(
    *,
    kind: str,
    source: str,
    text: str,
    tags: list[str],
    channel: str = "",
    session_id: str = "",
    role: str = "",
    user_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_store()
    with connect_db() as conn:
        entry = create_semantic_entry(
            conn,
            kind=kind,
            source=source,
            text=text.strip(),
            tags=tags,
            channel=channel,
            session_id=session_id,
            role=role,
            user_id=user_id,
            metadata=metadata or {},
        )
        upsert_semantic_entry(conn, entry)
        conn.commit()
        sync_compatibility_export(conn)
    try_sync_openclaw_workspace_memory()
    return compatibility_entry(entry)


def ingest_event(
    *,
    channel: str,
    session_id: str,
    role: str,
    user_id: str,
    source: str,
    kind: str,
    text: str,
    tags: list[str],
    metadata: dict[str, Any] | None = None,
    derive_memory: bool = True,
) -> dict[str, Any]:
    ensure_store()
    event = {
        "id": next_event_id(),
        "created_at": utc_now(),
        "channel": channel,
        "session_id": session_id,
        "role": role,
        "user_id": user_id,
        "source": source,
        "kind": kind,
        "tags": normalize_tags(tags),
        "text": text.strip(),
        "metadata": metadata or {},
        "derived_entry_id": "",
    }
    append_journal_event_file(event)

    memory_entry: dict[str, Any] | None = None
    with connect_db() as conn:
        if derive_memory:
            memory_entry = create_semantic_entry(
                conn,
                kind=kind,
                source=source,
                text=event["text"],
                tags=event["tags"],
                channel=channel,
                session_id=session_id,
                role=role,
                user_id=user_id,
                metadata=event["metadata"],
                created_at=event["created_at"],
            )
            upsert_semantic_entry(conn, memory_entry)
            event["derived_entry_id"] = memory_entry["id"]

        insert_journal_event(conn, event)
        conn.commit()
        sync_compatibility_export(conn)
    try_sync_openclaw_workspace_memory()

    return {
        "event_id": event["id"],
        "memory_id": event["derived_entry_id"],
        "stored": derive_memory,
        "channel": channel,
        "session_id": session_id,
    }


def build_fts_query(query: str) -> str:
    tokens = [token for token in re.findall(r"[A-Za-z0-9_]+", query.lower()) if len(token) > 1]
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens[:12])


def lexical_bonus_map(conn: sqlite3.Connection, query: str, limit: int) -> dict[str, float]:
    fts_query = build_fts_query(query)
    if not fts_query:
        return {}

    try:
        rows = conn.execute(
            """
            SELECT id
            FROM semantic_entries_fts
            WHERE semantic_entries_fts MATCH ?
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    bonuses: dict[str, float] = {}
    total = len(rows) or 1
    for index, row in enumerate(rows):
        bonuses[row["id"]] = max(bonuses.get(row["id"], 0.0), (total - index) / total)
    return bonuses


def search_memory_entries(query: str, limit: int) -> list[dict[str, Any]]:
    ensure_store()
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM semantic_entries
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        if not rows:
            return []

        query_embedding = normalize_embedding(embed_text(query))
        lexical_scores = lexical_bonus_map(conn, query, max(limit * 4, 12))
        scored: list[dict[str, Any]] = []

        for row in rows:
            entry = row_to_entry(row)
            vector_score = dot_product(query_embedding, unpack_embedding(row["embedding_blob"], row["embedding_dim"]))
            lexical_score = lexical_scores.get(entry["id"], 0.0)
            score = (vector_score * 0.88) + (lexical_score * 0.12)
            scored.append(
                {
                    "score": round(score, 4),
                    "vector_score": round(vector_score, 4),
                    "lexical_score": round(lexical_score, 4),
                    **compact_entry(entry),
                }
            )

    scored.sort(key=lambda item: (item["score"], item["created_at"], item["id"]), reverse=True)
    return scored[:limit]


def build_context(query: str, limit: int) -> str:
    matches = search_memory_entries(query, limit)
    if not matches:
        return "No memory entries found."

    blocks = []
    for entry in matches:
        facts = "\n".join(f"- {item}" for item in entry.get("facts", [])[:3]) or "- none"
        todo = "\n".join(f"- {item}" for item in entry.get("todo", [])[:3]) or "- none"
        constraints = "\n".join(f"- {item}" for item in entry.get("constraints", [])[:3]) or "- none"
        location = []
        if entry.get("channel"):
            location.append(f"channel={entry['channel']}")
        if entry.get("session_id"):
            location.append(f"session={entry['session_id']}")
        if entry.get("role"):
            location.append(f"role={entry['role']}")
        location_suffix = f" {' '.join(location)}" if location else ""
        blocks.append(
            textwrap.dedent(
                f"""\
                [{entry['id']}] score={entry['score']:.4f} kind={entry['kind']} source={entry['source']}{location_suffix}
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

    return "\n\n".join(blocks)


def list_memory_entries(limit: int) -> list[dict[str, Any]]:
    ensure_store()
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM semantic_entries
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [compatibility_entry(row_to_entry(row)) for row in rows]


def export_memory(output: Path, compact: bool) -> str:
    ensure_store()
    output.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM semantic_entries
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        with output.open("w", encoding="utf-8") as handle:
            for row in rows:
                entry = row_to_entry(row, include_embedding=not compact)
                record = compact_entry(entry) if compact else entry
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return str(output)


def normalize_import_entry(raw_entry: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    summary = raw_entry.get("summary") or truncate_text(raw_entry.get("text", ""))
    facts = raw_entry.get("facts", [])
    todo = raw_entry.get("todo", [])
    constraints = raw_entry.get("constraints", [])
    text = raw_entry.get("text") or summary
    embedding = raw_entry.get("embedding")
    if not embedding:
        embedding_seed = build_embedding_text(summary, facts, todo, constraints)
        embedding = normalize_embedding(embed_text(embedding_seed))

    return {
        "id": raw_entry.get("id") or fallback_id,
        "created_at": raw_entry.get("created_at") or utc_now(),
        "ingested_at": utc_now(),
        "kind": raw_entry.get("kind", "memory"),
        "source": raw_entry.get("source", "restore"),
        "channel": raw_entry.get("channel", ""),
        "session_id": raw_entry.get("session_id", ""),
        "role": raw_entry.get("role", ""),
        "user_id": raw_entry.get("user_id", ""),
        "tags": normalize_tags(raw_entry.get("tags", [])),
        "summary": summary,
        "text": text,
        "facts": facts,
        "todo": todo,
        "constraints": constraints,
        "metadata": normalize_metadata(raw_entry.get("metadata", {})),
        "embedding": normalize_embedding(embedding),
    }


def bootstrap_semantic_store(conn: sqlite3.Connection) -> None:
    existing_count = conn.execute("SELECT COUNT(*) AS count FROM semantic_entries").fetchone()["count"]
    if existing_count > 0:
        return
    if not MEMORY_DB.exists() or MEMORY_DB.stat().st_size == 0:
        return

    imported_entries: list[dict[str, Any]] = []
    with MEMORY_DB.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            raw_entry = json.loads(line)
            imported_entries.append(normalize_import_entry(raw_entry, f"mem-bootstrap-{len(imported_entries) + 1:06d}"))

    if not imported_entries:
        return

    for entry in imported_entries:
        upsert_semantic_entry(conn, entry)
    conn.commit()
    sync_compatibility_export(conn)


def import_memory(input_path: Path, replace: bool) -> int:
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    imported_entries: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            raw_entry = json.loads(line)
            imported_entries.append(normalize_import_entry(raw_entry, f"mem-import-{len(imported_entries) + 1:06d}"))

    ensure_store()
    with connect_db() as conn:
        if replace:
            conn.execute("DELETE FROM semantic_entries")
            conn.execute("DELETE FROM semantic_entries_fts")
            rebuild_journal_table(conn)
        for entry in imported_entries:
            upsert_semantic_entry(conn, entry)
        conn.commit()
        sync_compatibility_export(conn)
    try_sync_openclaw_workspace_memory()
    return len(imported_entries)


def memory_stats() -> dict[str, Any]:
    ensure_store()
    with connect_db() as conn:
        entry_count = conn.execute("SELECT COUNT(*) AS count FROM semantic_entries").fetchone()["count"]
        journal_count = conn.execute("SELECT COUNT(*) AS count FROM journal_events").fetchone()["count"]
        last_entry = conn.execute(
            "SELECT id, created_at FROM semantic_entries ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        last_event = conn.execute(
            "SELECT id, created_at FROM journal_events ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()

    return {
        "state_dir": str(LOCAL_LLM_DIR),
        "memory_dir": str(MEMORY_DIR),
        "semantic_db": str(MEMORY_SQLITE_DB),
        "journal_file": str(MEMORY_JOURNAL),
        "entries_export": str(MEMORY_DB),
        "semantic_entries": entry_count,
        "journal_events": journal_count,
        "semantic_db_bytes": MEMORY_SQLITE_DB.stat().st_size if MEMORY_SQLITE_DB.exists() else 0,
        "journal_bytes": MEMORY_JOURNAL.stat().st_size if MEMORY_JOURNAL.exists() else 0,
        "entries_export_bytes": MEMORY_DB.stat().st_size if MEMORY_DB.exists() else 0,
        "last_entry": dict(last_entry) if last_entry else None,
        "last_event": dict(last_event) if last_event else None,
    }


def add_entry(args: argparse.Namespace) -> int:
    entry = add_memory_entry(
        kind=args.kind,
        source=args.source,
        text=args.text,
        tags=normalize_tags(args.tags),
    )
    print(entry["id"])
    return 0


def ingest_entry(args: argparse.Namespace) -> int:
    result = ingest_event(
        channel=args.channel,
        session_id=args.session_id,
        role=args.role,
        user_id=args.user_id,
        source=args.source,
        kind=args.kind,
        text=args.text,
        tags=normalize_tags(args.tags),
        metadata=normalize_metadata(args.metadata),
        derive_memory=not args.skip_memory,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


def search_entries(args: argparse.Namespace) -> int:
    print(json.dumps(search_memory_entries(args.query, args.limit), indent=2, ensure_ascii=True))
    return 0


def context_block(args: argparse.Namespace) -> int:
    print(build_context(args.query, args.limit))
    return 0


def list_entries(args: argparse.Namespace) -> int:
    print(json.dumps(list_memory_entries(args.limit), indent=2, ensure_ascii=True))
    return 0


def export_entries(args: argparse.Namespace) -> int:
    print(export_memory(Path(args.output), compact=args.compact))
    return 0


def import_entries(args: argparse.Namespace) -> int:
    print(import_memory(Path(args.input), replace=args.replace))
    return 0


def stats_command(args: argparse.Namespace) -> int:
    print(json.dumps(memory_stats(), indent=2, ensure_ascii=True))
    return 0


def sync_openclaw_workspace_command(args: argparse.Namespace) -> int:
    sync_openclaw_workspace_memory()
    print(str(OPENCLAW_MEMORY_FILE))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freewiller hybrid memory store with journal, SQLite, and vector retrieval.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--kind", required=True)
    add_parser.add_argument("--source", required=True)
    add_parser.add_argument("--text", required=True)
    add_parser.add_argument("--tags", default="")
    add_parser.set_defaults(func=add_entry)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--channel", default="local")
    ingest_parser.add_argument("--session-id", default="")
    ingest_parser.add_argument("--role", default="user")
    ingest_parser.add_argument("--user-id", default="")
    ingest_parser.add_argument("--source", default="session")
    ingest_parser.add_argument("--kind", default="event")
    ingest_parser.add_argument("--text", required=True)
    ingest_parser.add_argument("--tags", default="")
    ingest_parser.add_argument("--metadata", default="{}")
    ingest_parser.add_argument("--skip-memory", action="store_true")
    ingest_parser.set_defaults(func=ingest_entry)

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

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--compact", action="store_true")
    export_parser.set_defaults(func=export_entries)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--input", required=True)
    import_parser.add_argument("--replace", action="store_true")
    import_parser.set_defaults(func=import_entries)

    stats_parser = subparsers.add_parser("stats")
    stats_parser.set_defaults(func=stats_command)

    sync_openclaw_parser = subparsers.add_parser("sync-openclaw-workspace")
    sync_openclaw_parser.set_defaults(func=sync_openclaw_workspace_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
