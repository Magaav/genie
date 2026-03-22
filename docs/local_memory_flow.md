# Local Memory Flow

Freewiller uses a guarded local utility layer before remote escalation.

## Deployment Shape

- host bootstrap: `init.sh`
  - repo sync
  - SSH hardening
  - Docker install
  - Ollama install
  - model pull
- host runtime: Ollama on `127.0.0.1:11434`
- containerized app layer: `local-agent`
  - HTTP boundary for orchestration and dispatch
  - shared runtime state via bind mounts under `/var/lib/freewiller`

## Roles

- `bash/local_llm.sh`
  - local routing
  - local summarization
  - local extraction
  - local embeddings passthrough
- `bash/local_memory.py`
  - persistent memory store
  - embedding-backed retrieval
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
  - `POST /orchestrate`
  - `POST /dispatch`

## Storage

Runtime state lives outside the repo:

- config: `/var/lib/freewiller/local-llm.env`
- gateway config: `/var/lib/freewiller/freewiller-gateway.env`
- memory db: `/var/lib/freewiller/memory/entries.jsonl`
- remote packages: `/var/lib/freewiller/packages/`
- gateway responses: `/var/lib/freewiller/responses/`

Container assets live in the repo:

- compose: `/local/docker-compose.local-agent.yml`
- image build: `/local/docker/local-agent/Dockerfile`

Each memory entry stores:

- `id`
- `created_at`
- `kind`
- `source`
- `tags`
- `summary`
- `text`
- `facts`
- `todo`
- `constraints`
- `embedding`

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
5. Store useful outputs with:
   - `python3 /local/bash/local_memory.py add ...`
6. Before remote escalation, assemble relevant context with:
   - `python3 /local/bash/local_memory.py context --query ...`
7. Use `python3 /local/bash/local_agent.py orchestrate ...` to package:
   - current task
   - route decision
   - local summary or local skip marker
   - local extract or local skip marker
   - top retrieved memory
8. Use `python3 /local/bash/local_agent.py dispatch ...` to send the package to the Freewiller gateway.
9. Send only:
   - packaged task block
   - compressed recent context
   - required file/tool data
10. For automation, expose the same orchestration flow through the local agent HTTP service.

## Operational Rules

- Local model is not the default deep reasoner on this host.
- If local route/summarize/extract exceeds its timeout, fail closed.
- Long or architecture-grade tasks should skip local deliberation.
- Retrieval should use memory summaries and structured facts, not raw logs.
- Gateway dispatch expects an OpenClaw-compatible `POST /v1/responses` endpoint with bearer auth and an agent id.
- The dockerized local-agent service uses host networking on Linux and talks to host Ollama through `127.0.0.1:11434`.
- A fresh `init.sh` run should recreate both the host runtime and the containerized local-agent service.

## Example Commands

Add memory:

```bash
python3 /local/bash/local_memory.py add \
  --kind decision \
  --source session \
  --tags local,llm,memory \
  --text "Use qwen3:8b for local routing and nomic-embed-text for retrieval."
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
sudo bash /local/init.sh
```

Check service health:

```bash
curl -s http://127.0.0.1:18790/health
```
