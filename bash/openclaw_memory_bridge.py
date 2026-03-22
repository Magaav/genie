#!/usr/bin/env python3

import json
import os
import threading
import time
from pathlib import Path

import local_memory


QUEUE_ENABLED = os.environ.get("OPENCLAW_MEMORY_QUEUE_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
QUEUE_FILE = Path(
    os.environ.get(
        "OPENCLAW_MEMORY_QUEUE_FILE",
        "/local/bridge/openclaw/openclaw-memory-queue.jsonl",
    )
)
QUEUE_OFFSET_FILE = Path(
    os.environ.get(
        "OPENCLAW_MEMORY_QUEUE_OFFSET_FILE",
        str(local_memory.LOCAL_LLM_DIR / "bridge" / "openclaw-memory-queue.offset"),
    )
)
QUEUE_POLL_SECONDS = max(
    1,
    int(os.environ.get("OPENCLAW_MEMORY_QUEUE_POLL_SECONDS", "5")),
)


def _read_offset() -> int:
    if not QUEUE_OFFSET_FILE.exists():
        return 0
    try:
        return max(0, int(QUEUE_OFFSET_FILE.read_text(encoding="utf-8").strip() or "0"))
    except (ValueError, OSError):
        return 0


def _write_offset(offset: int) -> None:
    QUEUE_OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_OFFSET_FILE.write_text(str(max(0, offset)), encoding="utf-8")


def drain_queue_once() -> int:
    if not QUEUE_ENABLED or not QUEUE_FILE.exists():
        return 0

    current_size = QUEUE_FILE.stat().st_size
    offset = _read_offset()
    if offset > current_size:
        offset = 0

    with QUEUE_FILE.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        chunk = handle.read()

    if not chunk:
        return 0

    last_newline = chunk.rfind("\n")
    if last_newline < 0:
        return 0

    complete_chunk = chunk[:last_newline]
    new_offset = offset + last_newline + 1
    processed = 0

    for raw_line in complete_chunk.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        local_memory.ingest_event(
            channel=str(payload.get("channel", "openclaw")),
            session_id=str(payload.get("session_id", "")),
            role=str(payload.get("role", "user")),
            user_id=str(payload.get("user_id", "")),
            source=str(payload.get("source", "openclaw")),
            kind=str(payload.get("kind", "conversation")),
            text=str(payload.get("text", "")).strip(),
            tags=local_memory.normalize_tags(payload.get("tags", [])),
            metadata=local_memory.normalize_metadata(payload.get("metadata", {})),
            derive_memory=not bool(payload.get("skip_memory", False)),
        )
        processed += 1

    _write_offset(new_offset)
    return processed


def _worker(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            drain_queue_once()
        except Exception:
            pass
        stop_event.wait(QUEUE_POLL_SECONDS)


def start_queue_worker() -> threading.Event | None:
    if not QUEUE_ENABLED:
        return None
    stop_event = threading.Event()
    thread = threading.Thread(target=_worker, args=(stop_event,), name="openclaw-memory-bridge", daemon=True)
    thread.start()
    return stop_event


def main() -> int:
    try:
        processed = drain_queue_once()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
