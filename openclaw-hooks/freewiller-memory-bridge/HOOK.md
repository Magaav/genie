---
name: freewiller-memory-bridge
description: "Mirror OpenClaw inbound and outbound message events into Freewiller shared memory"
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "events": ["message:preprocessed", "message:sent"],
        "install": [{ "id": "freewiller", "kind": "bundled", "label": "Bundled with Freewiller" }],
      },
  }
---

# Freewiller Memory Bridge

Mirrors OpenClaw conversation events into the Freewiller shared memory substrate.

It listens to:

- `message:preprocessed` for inbound user content after OpenClaw has enriched the body
- `message:sent` for successful outbound assistant replies

The hook posts those events to the local Freewiller memory ingest endpoint so Telegram and future
OpenClaw-facing channels converge into the same durable memory journal.
