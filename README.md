# Freewiller

Freewiller is a bootstrapable local orchestration node for:

- host hardening
- Docker and Ollama setup
- a small local LLM worker
- shared local memory and retrieval
- a containerized local-agent HTTP service

This repo is meant to be spawned onto a brand new Ubuntu VM and rebuilt from Git.

## What A Fresh Spawn Creates

After a successful bootstrap, the VM will have:

- hardened SSH config
  - `PasswordAuthentication no`
  - `PermitRootLogin no`
- `ufw` enabled with `OpenSSH` allowed
- `fail2ban` enabled for SSH
- Docker installed and running
- Ollama installed and running
- local models pulled
  - `qwen3:0.6b`
  - `nomic-embed-text`
- the Freewiller local-agent container running on:
  - `http://127.0.0.1:18790`

Runtime state is stored under `/local`, but outside Git tracking:

- `/local/state/freewiller`
- `/local/log/freewiller`
- `/local/feed`
- `/local/backups`

These paths live under `/local` so you can inspect and evolve the running node from the same workspace, but they are still ignored by Git.

The repo-local secret file `/local/.env` is also ignored by Git and excluded from the Docker build context. Backups include it as `repo.env` so local bot tokens and similar bootstrap secrets can be restored onto a respawned node.

Phase 0A routing state also lives in runtime state:

- provider routing policy: `/local/state/freewiller/provider-routing.env`
- provider registry: `/local/state/freewiller/provider-registry.json`
- Brain Router discovery state: `/local/state/freewiller/telemetry/provider-discovery.json`
- provider health state: `/local/state/freewiller/telemetry/provider-health.json`
- provider benchmark scores: `/local/state/freewiller/telemetry/provider-benchmarks.json`
- provider usage ledger: `/local/state/freewiller/telemetry/provider-usage.jsonl`

Tracked provider templates and benchmark corpus live in:

- `config/provider-registry.template.json`
- `benchmarks/providers/*.json`

The shared memory layer is hybrid and compact:

- append-only event journal: `/local/state/freewiller/memory/journal.jsonl`
- SQLite semantic store: `/local/state/freewiller/memory/memory.sqlite3`
- compatibility export for inspection: `/local/state/freewiller/memory/entries.jsonl`

Retrieval uses:

- local embeddings from `nomic-embed-text`
- normalized vector similarity
- FTS5 lexical bonus inside SQLite

Phase 0B security metadata is now first-class in memory:

- `trust_class`
- `privacy_class`
- `source_type`
- `source_id`
- `source_provider`
- `source_model`
- `verification_status`
- `operator_confirmed`
- `policy_tags`

Current safety defaults:

- untrusted identity/policy rewrite attempts are journaled but not promoted into durable memory
- secret-class memory is excluded from OpenClaw workspace projections and remote context packaging by default
- a synchronized `/local/.openclaw/workspace/BOUNDARIES.md` projection carries the current prompt-boundary rules

The target next-stage memory architecture is specified in:

- [`docs/freewiller_memory_spec.md`](docs/freewiller_memory_spec.md)

The operating roadmap for how Freewiller should become more useful, reliable, and expansive over time is:

- [`docs/freewiller_roadmap.md`](docs/freewiller_roadmap.md)

The security model for trust, privacy, capability gates, and prompt-injection resistance is:

- [`docs/freewiller_security_architecture.md`](docs/freewiller_security_architecture.md)

## Requirements

- a brand new Ubuntu VM
- SSH key access to that VM before bootstrap starts

Important:

- `init.sh` hardens SSH and disables password authentication.
- Do not rely on password login for recovery.
- Make sure your cloud VM already has a valid SSH public key installed before running the bootstrap.

Tested flow:

- Ubuntu 24.04
- Oracle ARM64 VM

## Fastest Spawn

On the new VM, run:

```bash
sudo bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

That is the default public-repo path. No GitHub deploy key is required.

To restore memory from a prior backup during spawn:

```bash
sudo RESTORE_BACKUP_URL='https://example.com/freewiller-daily-2026-03-22.tar.gz' \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

You can also restore from a file already present on the VM:

```bash
sudo RESTORE_BACKUP_PATH=/tmp/freewiller-daily-2026-03-22.tar.gz \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/freewiller/master/init.sh | bash'
```

## What `init.sh` Does

`init.sh` will:

1. install minimal bootstrap packages
2. clone or update this repo into `/local`
3. run host hardening
4. install Docker
5. install Ollama
6. pull the default local models
7. optionally restore compact memory from a prior Freewiller backup
8. install hourly and daily backup cron jobs
9. build and start the `freewiller-local-agent` container

## After Bootstrap

Open a new shell so the `ubuntu` user picks up Docker group membership:

```bash
newgrp docker
```

Then verify the instance:

```bash
docker ps
ollama list
curl -s http://127.0.0.1:18790/health
curl -s http://127.0.0.1:18790/policy
curl -s http://127.0.0.1:18790/providers
curl -s 'http://127.0.0.1:18790/providers/ranking?task_class=summarize&privacy_class=public'
curl -s http://127.0.0.1:18790/providers/health
curl -s http://127.0.0.1:18790/providers/scorecards
curl -s http://127.0.0.1:18790/providers/discovery
curl -s http://127.0.0.1:18790/memory/stats
bash /local/bash/backup_freewiller.sh list
sudo crontab -l
```

Expected service:

- container: `freewiller-local-agent`
- health endpoint: `http://127.0.0.1:18790/health`

## Optional Modes

If you want only the hardened base host and repo sync, without the local LLM stack:

```bash
sudo INSTALL_LOCAL_LLM=0 INSTALL_LOCAL_AGENT_SERVICE=0 bash /local/init.sh
```

If you want to override the repo URL:

```bash
sudo REPO_URL=https://github.com/Magaav/freewiller.git bash /local/init.sh
```

If you want to use SSH cloning instead of public HTTPS, provide one of:

- `DEPLOY_KEY_B64`
- `DEPLOY_KEY_CONTENT`
- `DEPLOY_KEY_PATH`

Example:

```bash
sudo REPO_URL=git@github.com:Magaav/freewiller.git \
  DEPLOY_KEY_B64='BASE64_OF_PRIVATE_KEY' \
  bash /local/init.sh
```

## Gateway Configuration

Bootstrap does not configure a remote gateway token by default.

If you want Freewiller to dispatch packaged requests to a remote OpenClaw-compatible gateway, edit:

```bash
/local/state/freewiller/freewiller-gateway.env
```

Then restart the local-agent service:

```bash
bash /local/bash/install_local_agent_service.sh
```

If you want to add cheaper external lanes later, the human-facing control point is:

```bash
/local/.env
```

The machine-facing persisted routing state remains:

```bash
/local/state/freewiller/provider-routing.env
```

Freewiller will read `.env` during `bash /local/bash/install_local_llm.sh`, sync the explicit provider registry, and persist resolved routing state there. That means a respawn can recover cheap-lane settings from backup without you editing runtime files by hand.

That provider state controls:

- default privacy routing
- the explicit provider registry
- provider health and cooldown state
- benchmark quality scores
- the provider usage ledger location

The local-agent provider interfaces are:

- `GET /providers`
- `GET /providers/ranking`
- `GET /providers/health`
- `GET /providers/scorecards`
- `GET /providers/discovery`
- `POST /providers/evaluate`
- `POST /providers/discover`

The CLI interface is:

```bash
python3 /local/bash/provider_router.py providers
python3 /local/bash/provider_router.py rank --task-class summarize --privacy-class public
python3 /local/bash/provider_router.py health
python3 /local/bash/provider_router.py heartbeat
python3 /local/bash/provider_router.py scorecards --refresh
python3 /local/bash/provider_router.py discovery
python3 /local/bash/provider_router.py discover --provider-family nvidia --sync
python3 /local/bash/provider_router.py evaluate --profile summarize
```

Example NVIDIA cheap-lane config in `/local/.env`:

```bash
NVIDIA_API_KEY='your_nvidia_key'
```

Kimi K2.5 is wired in instant mode by default so it does not waste tokens on thinking traces. After updating `.env`, apply it with:

```bash
bash /local/bash/install_local_llm.sh
bash /local/bash/install_local_agent_service.sh
```

Freewiller now treats NVIDIA as one shared provider account. Put a single key in `/local/.env`:

- `NVIDIA_API_KEY`

The router will auto-enable the curated NVIDIA model catalog behind that key, including:

- `openai/gpt-oss-120b`
- `moonshotai/kimi-k2-instruct`
- `qwen/qwen3-next-80b-a3b-instruct`
- `moonshotai/kimi-k2.5`
- `z-ai/glm5`
- `z-ai/glm4.7`
- `deepseek-ai/deepseek-v3.1`
- `qwen/qwen3.5-397b-a17b`
- `nvidia/nemotron-3-nano-30b-a3b`

Unsupported dotted or malformed provider keys are ignored with warnings during registry sync. Do not use names like `NVIDEA_KIMI_K2.5_API_KEY`.

Freewiller keeps task-family scorecards under:

```bash
/local/state/freewiller/telemetry/provider-scorecards.json
```

It keeps provider discovery under:

```bash
/local/state/freewiller/telemetry/provider-discovery.json
```

It uses those scorecards plus live health to rank providers per task family, reserve slow-powerful models for background work, and fall back when the frontier lane is exhausted.

The frontier exhaustion switches are:

- `FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK=1`
- `FREEWILLER_FRONTIER_EXHAUSTED=0`

The subsystem that owns provider discovery, scoring, failover, and frontier preservation is documented in:

```bash
/local/docs/freewiller_brain_router.md
```

## OpenClaw Seed Integration

Freewiller treats OpenClaw as a seed capability source, not as a permanent moving dependency.

Current seed policy:

- import a verified upstream snapshot once
- pin the exact commit
- integrate against that pinned gateway and channel surface
- evolve Freewiller independently after that

The current pinned upstream seed is recorded in:

- [`docs/openclaw_seed_strategy.md`](docs/openclaw_seed_strategy.md)

And the installed node records the exact imported snapshot in:

- `/local/state/freewiller/openclaw-seed/seed.json`

To prepare the pinned OpenClaw seed locally:

```bash
sudo SUDO_USER=ubuntu bash /local/bash/install_openclaw.sh
```

That installer checks out the pinned upstream commit in detached-head mode so a fresh bootstrap does not silently drift with upstream `main`.

It also bootstraps the seed in the shape Freewiller expects:

- enables OpenClaw `POST /v1/responses` and `POST /v1/chat/completions`
- writes a compose override at `/local/state/freewiller/openclaw-seed/docker-compose.override.yml`
- if `/home/<user>/.codex/auth.json` exists, syncs that Codex auth into OpenClaw seed state
- when Codex auth is present, sets the default OpenClaw model to `openai-codex/gpt-5.4`
- rewrites `/local/state/freewiller/freewiller-gateway.env` for the local pinned gateway
- installs the Freewiller internal hook bridge into the OpenClaw workspace
- mirrors OpenClaw `message:preprocessed` and `message:sent` events into the shared memory substrate automatically

The automatic OpenClaw and Telegram memory bridge works like this:

- OpenClaw internal hooks append compact event payloads to `/local/.openclaw/workspace/freewiller-ingest/openclaw-memory-queue.jsonl`
- the dockerized local-agent drains that queue in the background
- each queued event is written into:
  - `/local/state/freewiller/memory/journal.jsonl`
  - `/local/state/freewiller/memory/memory.sqlite3`
- Freewiller also projects that shared memory back into the OpenClaw workspace files that the `main` agent reads:
  - `/local/.openclaw/workspace/IDENTITY.md`
  - `/local/.openclaw/workspace/USER.md`
  - `/local/.openclaw/workspace/MEMORY.md`
  - `/local/.openclaw/workspace/memory/YYYY-MM-DD.md`

That means Telegram and OpenClaw conversations can converge into the same memory substrate without calling `POST /memory/ingest` manually for each chat message.

## Backups And Respawn Memory

Bootstrap installs two root cron jobs by default:

- hourly snapshot at `HH:05`
- daily snapshot at `03:17 UTC`

Phase 0C also installs provider maintenance jobs into the root crontab:

- heartbeat every `10` minutes
- non-frontier benchmark run every `6` hours
- targeted frontier-judged recalibration once daily

Backups are stored in:

- `/local/backups/hourly`
- `/local/backups/daily`

Retention is intentionally small:

- keep the last `3` hourly backups
- keep the last `1` daily backup

Each archive contains a compact recovery bundle:

- `repo.env` from `/local/.env` if present
- `local-llm.env`
- `freewiller-gateway.env` if present
- `provider-routing.env` if present
- `provider-registry.json` if present
- `telemetry/provider-health.json` if present
- `telemetry/provider-benchmarks.json` if present
- `telemetry/provider-usage.jsonl` if present
- `journal.jsonl`
- compact memory export with summaries, facts, TODOs, and constraints
- `manifest.json`

## Shared Memory API

Any endpoint that wants continuity should write to the shared memory API instead of keeping its own private state.

Current local-agent memory endpoints:

- `GET /memory/stats`
- `POST /memory/ingest`
- `POST /memory/search`
- `POST /memory/context`

Example ingest:

```bash
curl -s -X POST http://127.0.0.1:18790/memory/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "telegram",
    "session_id": "dm-8286257781",
    "role": "user",
    "user_id": "8286257781",
    "source": "telegram",
    "kind": "conversation",
    "tags": ["telegram", "dm"],
    "text": "Keep a single shared memory substrate across endpoints."
  }'
```

Optional security fields for ingest:

- `trust_class`
- `privacy_class`
- `source_type`
- `source_id`
- `source_provider`
- `source_model`
- `verification_status`
- `operator_confirmed`
- `policy_tags`

If you omit them, Freewiller infers them from the channel, source, metadata, and text.

If an event looks like an untrusted attempt to rewrite identity, policy, or permissions, it is still journaled for audit but returned with:

- `stored: false`
- `promotion_blocked: true`
- `promotion_reason: blocked_untrusted_policy_rewrite`

Example hybrid retrieval:

```bash
curl -s -X POST http://127.0.0.1:18790/memory/context \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "single shared memory substrate",
    "limit": 3
  }'
```

On restore, embeddings are rebuilt locally from the compact memory export so a respawn can recover its prior memory state without carrying the full raw runtime tree. If `/local/.env` existed when the backup was made, it is restored too.

Manual `POST /memory/ingest` is still useful for:

- IDE continuity notes
- imported notes from other systems
- one-off operator instructions

OpenClaw and Telegram message events are mirrored automatically once the pinned seed is installed.

Manual commands:

```bash
bash /local/bash/backup_freewiller.sh save hourly
bash /local/bash/backup_freewiller.sh save daily
bash /local/bash/backup_freewiller.sh list
bash /local/bash/backup_freewiller.sh restore /local/backups/daily/freewiller-daily-YYYY-MM-DD.tar.gz
```

## Recover Old Agent Progress

If you have a backup from an older Freewiller node and want this instance to inherit that prior memory:

1. Drop the archive into `/local/feed`.
2. Restore it into the live state directory.
3. Restart the local-agent service.
4. Continue talking to the agent with the recovered memory now present on disk.

Example:

```bash
mkdir -p /local/feed
cp /path/to/freewiller-daily-YYYY-MM-DD.tar.gz /local/feed/
bash /local/bash/backup_freewiller.sh restore /local/feed/freewiller-daily-YYYY-MM-DD.tar.gz --force
bash /local/bash/install_local_agent_service.sh
```

After that, the prior memory is restored into:

- `/local/state/freewiller/memory/entries.jsonl`

So if you then ask the agent to integrate or continue from its old progress, it is already operating on the recovered memory base.

If you want to do this during the very first spawn instead of after the machine is already up, use `RESTORE_BACKUP_PATH` or `RESTORE_BACKUP_URL` with `init.sh` as shown above.

## Local Runtime

Current default local worker:

- `qwen3:0.6b`

Current embedding model:

- `nomic-embed-text`

That model choice is intentional for this class of small CPU VM. Larger local models were too slow for routing and summarization on this hardware.

## Main Files

- [`init.sh`](init.sh)
- [`docs/local_memory_flow.md`](docs/local_memory_flow.md)
- [`bash/local_llm.sh`](bash/local_llm.sh)
- [`bash/local_memory.py`](bash/local_memory.py)
- [`bash/local_agent.py`](bash/local_agent.py)
- [`bash/local_agent_http.py`](bash/local_agent_http.py)
- [`bash/provider_router.py`](bash/provider_router.py)
- [`bash/backup_freewiller.sh`](bash/backup_freewiller.sh)
- [`bash/cronjob_freewiller.sh`](bash/cronjob_freewiller.sh)
- [`docker-compose.local-agent.yml`](docker-compose.local-agent.yml)

## Troubleshooting

If bootstrap completes but Docker commands fail for `ubuntu`, open a new shell or run:

```bash
newgrp docker
```

If the local-agent container is not healthy:

```bash
docker compose -f /local/docker-compose.local-agent.yml logs -f local-agent
```

If Ollama is not responding:

```bash
systemctl status ollama --no-pager
curl -s http://127.0.0.1:11434/api/tags
```
