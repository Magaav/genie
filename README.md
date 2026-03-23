# Genie

Genie is a bootstrapable native agent node.

It is designed to respawn onto a fresh Ubuntu VM, recover its local state, and keep operating through a small set of explicit services:

- `gateway`
- `ethics`
- `memory`
- `brain`

Current runtime paths:

- repo slug: `Magaav/genie`
- state: `/local/state/genie`
- logs: `/local/log/genie`

The runtime identity is now `Genie`.

## Native Node Shape

Top level stays intentionally small:

- `/local/init.sh`
- `/local/README.md`
- `/local/.gitignore`
- `/local/docker`
- `/local/services`
- `/local/bash`
- `/local/config`
- `/local/docs`
- `/local/state`
- `/local/log`
- `/local/backups`
- `/local/feed`

Docker runtime files live under:

- `/local/docker/compose.yml`
- `/local/docker/access.env`
- `/local/docker/conf.env`

Per-service build contexts live under:

- `/local/services/gateway`
- `/local/services/ethics`
- `/local/services/memory`
- `/local/services/brain`

## Spirit, Soul, Body

Genie uses a simple control model:

- `spirit`
  - the human operator for now
  - source of mission, permission, and long-horizon direction
- `soul`
  - the `ethics` layer plus native projections
  - where intent, memory, and boundaries converge
- `body`
  - the running machinery
  - `gateway`, `memory`, `brain`, host Ollama, Docker, cron, filesystems, backups

Full architecture note:

- [`docs/genie_native_architecture.md`](docs/genie_native_architecture.md)

## Service Responsibilities

### `gateway`

The public surface.

It owns:

- local HTTP API
- Telegram integration
- inbound event normalization
- response delivery

### `ethics`

The orchestration layer.

It owns:

- task decomposition
- working-state assembly
- policy-aware execution mediation
- calling `memory` for context
- calling `brain` for provider selection and remote execution

### `memory`

The canonical continuity layer.

It owns:

- append-only journal
- SQLite semantic memory
- search and context assembly
- projection files
- export/import and respawn restore hooks

### `brain`

The Brain Router service.

It owns:

- provider registry
- provider discovery
- health and cooldown state
- benchmark scorecards
- failover
- provider execution lanes

## Runtime State

Runtime state lives under `/local` but is ignored by Git:

- `/local/state/genie`
- `/local/log/genie`
- `/local/backups`
- `/local/feed`

The runtime env is split into:

- `/local/docker/access.env`
- `/local/docker/conf.env`

Backups include both files, so secrets and runtime configuration can respawn with the node.

## Memory Layout

Canonical memory lives in:

- journal: `/local/state/genie/memory/journal.jsonl`
- semantic DB: `/local/state/genie/memory/memory.sqlite3`
- compatibility export: `/local/state/genie/memory/entries.jsonl`

Native projections live in:

- `/local/state/genie/projections/IDENTITY.md`
- `/local/state/genie/projections/USER.md`
- `/local/state/genie/projections/MEMORY.md`
- `/local/state/genie/projections/BOUNDARIES.md`
- `/local/state/genie/projections/PROJECT_STATE.md`

## Provider State

Brain Router state lives in:

- `/local/state/genie/provider-routing.env`
- `/local/state/genie/provider-registry.json`
- `/local/state/genie/telemetry/provider-health.json`
- `/local/state/genie/telemetry/provider-benchmarks.json`
- `/local/state/genie/telemetry/provider-scorecards.json`
- `/local/state/genie/telemetry/provider-discovery.json`
- `/local/state/genie/telemetry/provider-usage.jsonl`

Tracked templates and benchmark corpus live in:

- `config/provider-registry.template.json`
- `benchmarks/providers/*.json`

## Fresh Spawn

On a fresh Ubuntu VM:

```bash
sudo bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/genie/master/init.sh | bash'
```

To restore state from an existing backup during spawn:

```bash
sudo RESTORE_BACKUP_URL='https://example.com/genie-daily-2026-03-23.tar.gz' \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/genie/master/init.sh | bash'
```

Or from a file already on the VM:

```bash
sudo RESTORE_BACKUP_PATH=/tmp/genie-daily-2026-03-23.tar.gz \
  bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/genie/master/init.sh | bash'
```

## What `init.sh` Does

`init.sh`:

1. installs minimal bootstrap packages
2. clones or updates the repo into `/local`
3. hardens the host
4. installs Docker
5. installs Ollama on the host
6. pulls the local models
7. restores a backup if requested
8. installs cron jobs
9. starts the native Genie stack from `/local/docker/compose.yml`

## Environment File

Operator-controlled runtime secrets belong in:

```bash
/local/docker/access.env
/local/docker/conf.env
```

Examples:

```bash
# /local/docker/access.env
TELEGRAM_BOT_TOKEN='...'
NVIDIA_API_KEY='...'
OPENROUTER_API_KEY='...'

# /local/docker/conf.env
OPENROUTER_MODEL='openrouter/free'
OPENROUTER_FREE_ONLY='1'
GENIE_GATEWAY_PORT='18790'
GENIE_TELEGRAM_ENABLED='1'
```

Do not use root-level `/local/.env` anymore.

`bash /local/bash/install_local_llm.sh` will read both `/local/docker/access.env` and `/local/docker/conf.env`, sync provider configuration, and persist resolved routing state.

When `NVIDIA_API_KEY` or `OPENROUTER_API_KEY` is present, Brain Router also discovers the live provider catalogs and imports bounded benchmark-pending candidates automatically.

The recommended OpenRouter baseline while frontier usage is scarce is:

- `OPENROUTER_MODEL='openrouter/free'`
- `OPENROUTER_FREE_ONLY='1'`

That keeps Genie on the free router and only imports free OpenRouter candidates until you deliberately opt into paid lanes.

## Start And Verify

Open a new shell after bootstrap so Docker group membership is active:

```bash
newgrp docker
```

Bring the native stack up manually:

```bash
docker compose \
  --env-file /local/docker/conf.env \
  --env-file /local/docker/access.env \
  -f /local/docker/compose.yml up -d --build
```

Verify it:

```bash
docker ps
ollama list
curl -s http://127.0.0.1:18790/health
curl -s http://127.0.0.1:18790/policy
curl -s http://127.0.0.1:18790/providers
curl -s http://127.0.0.1:18790/memory/stats
```

Expected services:

- `genie-gateway`
- `genie-ethics`
- `genie-memory`
- `genie-brain`

Useful aliases installed by bootstrap:

- `genie-up`
- `genie-logs`
- `genie-backup`

## Shadow Mode

Use shadow mode before taking over the live port or Telegram surface:

```bash
GENIE_GATEWAY_PORT=28790 GENIE_TELEGRAM_ENABLED=0 \
  docker compose \
    --env-file /local/docker/conf.env \
    --env-file /local/docker/access.env \
    -f /local/docker/compose.yml up -d --build
```

This keeps the native stack isolated on `127.0.0.1:28790`.

## HTTP API

The `gateway` service exposes:

- `GET /health`
- `GET /policy`
- `GET /providers`
- `GET /providers/ranking`
- `GET /providers/health`
- `GET /providers/scorecards`
- `GET /providers/discovery`
- `GET /memory/stats`
- `POST /memory/ingest`
- `POST /memory/search`
- `POST /memory/context`
- `POST /memory/sync-projections`
- `POST /providers/evaluate`
- `POST /providers/discover`
- `POST /orchestrate`
- `POST /dispatch`

## Telegram

Telegram support is native to `gateway`.

It uses long polling and reads:

- `TELEGRAM_BOT_TOKEN`
- `GENIE_TELEGRAM_ENABLED`

Allowlist state lives in:

- `/local/state/genie/gateway/telegram-allowlist.json`

## Brain Router

Brain Router is the adaptive provider-selection subsystem.

It currently:

- ranks providers by task family
- discovers the live NVIDIA catalog
- keeps leader and backup lanes
- benchmarks providers
- degrades and cools down bad lanes
- preserves the frontier lane for higher-trust work

Main docs:

- [`docs/genie_brain_router.md`](docs/genie_brain_router.md)
- [`docs/genie_security_architecture.md`](docs/genie_security_architecture.md)
- [`docs/genie_roadmap.md`](docs/genie_roadmap.md)

## Frontier Adapter

Genie no longer uses OpenClaw as its native runtime shape.

But the current frontier adapter can still point at an OpenClaw-compatible gateway if one is configured in:

```bash
/local/state/genie/genie-gateway.env
```

That keeps the strongest GPT-class lane available without making OpenClaw part of the native four-service node.

## Backups And Restore

Bootstrap installs:

- hourly snapshots
- daily snapshots
- provider heartbeat and evaluation cron jobs

Backup locations:

- `/local/backups/hourly`
- `/local/backups/daily`

Backups include:

- `/local/docker/access.env`
- `/local/docker/conf.env`
- memory journal and SQLite store
- projection files
- provider registry/routing/telemetry
- gateway state
- compact memory export

Manual commands:

```bash
bash /local/bash/backup_genie.sh save hourly
bash /local/bash/backup_genie.sh save daily
bash /local/bash/backup_genie.sh list
bash /local/bash/backup_genie.sh restore /local/backups/daily/<archive>.tar.gz --force
```

To inherit an older node’s progress:

```bash
mkdir -p /local/feed
cp /path/to/backup.tar.gz /local/feed/
bash /local/bash/backup_genie.sh restore /local/feed/backup.tar.gz --force
bash /local/bash/install_local_agent_service.sh
```

## Current Security Model

The native node is built around:

- trust classes
- privacy classes
- provenance
- prompt-injection resistance
- memory poisoning resistance

Untrusted attempts to rewrite identity or policy are journaled for audit but blocked from durable promotion.

## Compatibility Notes

The runtime identity, service names, state path, and native architecture are now `Genie`.

The GitHub repo slug is now aligned with the runtime identity:

- `Magaav/genie`
