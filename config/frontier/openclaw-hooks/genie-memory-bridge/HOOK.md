---
name: genie-memory-bridge
description: "Mirror OpenClaw inbound and outbound message events into Genie shared memory"
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "events": ["message:preprocessed", "message:sent"],
        "install": [{ "id": "genie", "kind": "bundled", "label": "Bundled with Genie" }],
      },
  }
---

# Genie Memory Bridge

Mirrors OpenClaw conversation events into the Genie shared memory substrate.

It listens to:

- `message:preprocessed` for inbound user content after OpenClaw has enriched the body
- `message:sent` for successful outbound assistant replies

The hook posts those events to the local Genie memory ingest endpoint so Telegram and future
OpenClaw-facing channels converge into the same durable memory journal.
