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
6. The semantic store derives summary, facts, TODOs, constraints, and embeddings from that event.
7. Before remote escalation, assemble relevant context with:
   - `python3 /local/bash/local_memory.py context --query ...`
8. Use `python3 /local/bash/local_agent.py orchestrate ...` to package:
   - current task
   - route decision
   - local summary or local skip marker
   - local extract or local skip marker
   - top retrieved memory
9. Use `python3 /local/bash/local_agent.py dispatch ...` to send the package to the Freewiller gateway.
10. Send only:
   - packaged task block
   - compressed recent context
   - required file/tool data
11. For automation, expose the same orchestration flow through the local agent HTTP service.

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
