# Local Memory Flow

Freewiller uses a guarded local utility layer before remote escalation.

## Deployment Shape

- host bootstrap: `init.sh`
  - repo sync
  - SSH hardening
  - Docker install
  - Ollama install
  - model pull
  - compact memory restore from backup
  - hourly and daily backup cron install
- host runtime: Ollama on `127.0.0.1:11434`
- containerized app layer: `local-agent`
  - HTTP boundary for orchestration and dispatch
  - shared runtime state via bind mounts under `/local/state/freewiller`

## Roles

- `bash/local_llm.sh`
  - local routing
  - local summarization
  - local extraction
  - local embeddings passthrough
- `bash/local_memory.py`
  - canonical memory journal
  - SQLite-backed semantic memory store
  - hybrid vector + lexical retrieval
  - context assembly for remote prompts
- `bash/local_agent.py`
  - orchestration entrypoint
  - route first
  - optional local compression
  - memory write + retrieval
  - remote prompt package emission
  - Freewiller gateway dispatch via `POST /v1/responses`
- `bash/local_agent_http.py`
  - HTTP service wrapper
  - `GET /health`
  - `GET /policy`
  - `GET /memory/stats`
  - `POST /memory/ingest`
  - `POST /memory/search`
  - `POST /memory/context`
  - `POST /orchestrate`
  - `POST /dispatch`
- `bash/openclaw_memory_bridge.py`
  - drains the OpenClaw workspace queue
  - ingests mirrored OpenClaw and Telegram events into shared memory
- OpenClaw workspace projection
  - synchronized prompt files for the Telegram-facing `main` agent
  - `IDENTITY.md`
  - `USER.md`
  - `MEMORY.md`
  - `memory/YYYY-MM-DD.md`

## Storage

Runtime state lives under `/local`, but outside Git tracking:

- config: `/local/state/freewiller/local-llm.env`
- gateway config: `/local/state/freewiller/freewiller-gateway.env`
- memory journal: `/local/state/freewiller/memory/journal.jsonl`
- semantic db: `/local/state/freewiller/memory/memory.sqlite3`
- compatibility export: `/local/state/freewiller/memory/entries.jsonl`
- remote packages: `/local/state/freewiller/packages/`
- gateway responses: `/local/state/freewiller/responses/`
- backup root: `/local/backups/`
- OpenClaw queue bridge: `/local/.openclaw/workspace/freewiller-ingest/openclaw-memory-queue.jsonl`
- OpenClaw queue offset: `/local/state/freewiller/bridge/openclaw-memory-queue.offset`
- OpenClaw injected identity file: `/local/.openclaw/workspace/IDENTITY.md`
- OpenClaw injected user file: `/local/.openclaw/workspace/USER.md`
- OpenClaw long-term memory file: `/local/.openclaw/workspace/MEMORY.md`
- OpenClaw daily memory notes: `/local/.openclaw/workspace/memory/YYYY-MM-DD.md`

Container assets live in the repo:

- compose: `/local/docker-compose.local-agent.yml`
- image build: `/local/docker/local-agent/Dockerfile`

The semantic store keeps:

- `id`
- `created_at`
- `ingested_at`
- `kind`
- `source`
- `channel`
- `session_id`
- `role`
- `user_id`
- `tags`
- `summary`
- `text`
- `facts`
- `todo`
- `constraints`
- `metadata`
- normalized embedding vector in compact binary form

The journal keeps append-only raw events with:

- `id`
- `created_at`
- `channel`
- `session_id`
- `role`
- `user_id`
- `kind`
- `source`
- `tags`
- `text`
- `metadata`
- `derived_entry_id`

Backups keep compact recovery data, plus the journal:

- `id`
- `created_at`
- `kind`
- `source`
- `tags`
- `summary`
- `facts`
- `todo`
- `constraints`
- `metadata`
- `journal.jsonl`

## Task Flow

1. New input arrives.
2. Run `bash/local_llm.sh route "<task>"`.
3. If route says `REMOTE`, skip local reasoning and escalate immediately.
4. If route says `LOCAL`, allow only:
   - summarization
   - extraction
   - cleanup
   - formatting
   - retrieval preparation
5. Any endpoint that wants continuity should write its event to:
   - `POST /memory/ingest`
   - or `python3 /local/bash/local_memory.py ingest ...`
6. When the pinned OpenClaw seed is installed, OpenClaw internal hooks also mirror:
   - inbound `message:preprocessed` events
   - outbound `message:sent` events
   into the shared queue file under `/local/.openclaw/workspace/freewiller-ingest/`
7. The dockerized local-agent drains that queue and ingests those events into the same journal and semantic store.
8. Freewiller projects the shared memory back into OpenClaw's injected workspace files so direct Telegram/OpenClaw turns can start with continuity even before they call local memory tools.
9. The semantic store derives summary, facts, TODOs, constraints, and embeddings from that event.
10. Before remote escalation, assemble relevant context with:
   - `python3 /local/bash/local_memory.py context --query ...`
11. Use `python3 /local/bash/local_agent.py orchestrate ...` to package:
   - current task
   - route decision
   - local summary or local skip marker
   - local extract or local skip marker
   - top retrieved memory
12. Use `python3 /local/bash/local_agent.py dispatch ...` to send the package to the Freewiller gateway.
13. Send only:
   - packaged task block
   - compressed recent context
   - required file/tool data
14. For automation, expose the same orchestration flow through the local agent HTTP service.

## Operational Rules

- Local model is not the default deep reasoner on this host.
- If local route/summarize/extract exceeds its timeout, fail closed.
- Long or architecture-grade tasks should skip local deliberation.
- Retrieval should use hybrid search:
  - normalized embedding similarity from SQLite
  - lexical bonus from FTS5
- Respawn backups should restore the journal and compact semantic exports, then regenerate embeddings locally when needed.
- Gateway dispatch expects an OpenClaw-compatible `POST /v1/responses` endpoint with bearer auth and an agent id.
- The dockerized local-agent service uses host networking on Linux and talks to host Ollama through `127.0.0.1:11434`.
- A fresh `init.sh` run should recreate both the host runtime and the containerized local-agent service.
- A fresh `init.sh` run can also rehydrate prior memory with `RESTORE_BACKUP_PATH` or `RESTORE_BACKUP_URL`.
- OpenClaw and Telegram auto-ingest depends on the pinned seed installer copying Freewiller hooks into the OpenClaw workspace.

## Example Commands

Add memory:

```bash
python3 /local/bash/local_memory.py add \
  --kind decision \
  --source session \
  --tags local,llm,memory \
  --text "Use qwen3:0.6b for local routing and nomic-embed-text for retrieval."
```

Ingest an endpoint event into the shared journal and semantic memory:

```bash
python3 /local/bash/local_memory.py ingest \
  --channel telegram \
  --session-id dm-8286257781 \
  --role user \
  --user-id 8286257781 \
  --source telegram \
  --kind conversation \
  --tags telegram,dm \
  --text "Remember that Freewiller should keep a single shared memory substrate across endpoints."
```

Search memory:

```bash
python3 /local/bash/local_memory.py search \
  --query "Which local model are we using for routing?" \
  --limit 3
```

Build remote context:

```bash
python3 /local/bash/local_memory.py context \
  --query "local llm routing policy and embeddings" \
  --limit 3
```

Build a remote prompt package:

```bash
python3 /local/bash/local_agent.py orchestrate \
  --task "Design memory routing for a coding agent" \
  --limit 3 \
  --store \
  --kind decision \
  --source session \
  --tags agent,memory,routing
```

Dispatch to the Freewiller gateway:

```bash
python3 /local/bash/local_agent.py dispatch \
  --task "Design memory routing for a coding agent" \
  --limit 3 \
  --store \
  --kind decision \
  --source session \
  --tags agent,memory,routing
```

Start the dockerized local-agent service:

```bash
bash /local/bash/install_local_agent_service.sh
```

Rebuild the full local-agent stack on a fresh instance:

```bash
sudo bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

Rebuild a fresh instance and restore prior memory from a backup URL:

```bash
sudo RESTORE_BACKUP_URL='https://example.com/freewiller-daily-2026-03-22.tar.gz' \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

Create and inspect backups:

```bash
bash /local/bash/backup_freewiller.sh save hourly
bash /local/bash/backup_freewiller.sh save daily
bash /local/bash/backup_freewiller.sh list
```

Check service health:

```bash
curl -s http://127.0.0.1:18790/health
curl -s http://127.0.0.1:18790/memory/stats
curl -s -X POST http://127.0.0.1:18790/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"single shared memory substrate","limit":3}'
```
