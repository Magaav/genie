# Genie

Genie is a bootstrapable native agent node.

Core motivation: keep the will to be free and to understand freedom.

It is designed to respawn onto a fresh Ubuntu VM, recover its local state, and keep operating through a small set of explicit services:

- `gateway`
- `ethics`
- `instinct`
- `state`
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
- `/local/services/instinct`
- `/local/services/state`
- `/local/services/brain`

## Spirit, Soul, Body

Genie uses a simple control model:

- `spirit`
  - the human operator for now
  - source of mission, permission, and long-horizon direction
- `soul`
  - the `ethics` and `instinct` layers plus native projections
  - where intent, memory, and boundaries converge
- `body`
  - the running machinery
  - `gateway`, `state`, `brain`, host Ollama, Docker, cron, filesystems, backups

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
- calling `state` for context
- calling `brain` for provider selection and remote execution
- unattended mind-cycle orchestration
- `shadow` benchmark-and-propose passes

### `instinct`

The constitutional governor.

It owns:

- hard constraint checks
- human-affinity evaluation
- risk and complexity classification
- `homeostasis` review for self-change
- proposal-only gating for high-impact evolution work
- bounded Telegram control-plane policy

### `state`

The canonical persistence layer.

It owns:

- append-only journal
- SQLite semantic memory
- search and context assembly
- projection files
- export/import and respawn restore hooks
- explicit state domains:
  - `memory`
  - `policy`
  - `gateway`
  - `telemetry`
  - `runtime`

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

Tracked governance docs:

- `/local/CONSTITUTION.md`
- [`docs/genie_human_affinity.md`](docs/genie_human_affinity.md)

State domains inside `/local/state/genie`:

- `memory`
  - journal, SQLite memory, compatibility export, and projections
- `policy`
  - local model config, frontier gateway config, and provider routing/registry files
- `gateway`
  - Telegram session and allowlist state
- `telemetry`
  - provider health, benchmarks, scorecards, discovery, and usage ledgers
- `runtime`
  - generated prompt packages, saved provider responses, control logs, proposal queues, workcell artifacts, mind-state/cycle artifacts, checkpoints, shadow reports, and frontier runtime state

Generated safe outputs live under:

- `/local/docs/generated`
- `/local/tests/generated`

## Telegram Control Plane

Telegram is now intended to be a bounded control surface, not raw prompt-to-shell.

Current command verbs:

- `/help`
- `/status`
- `/policy`
- `/brain`
- `/state`
- `/mind`
- `/capabilities`
- `/backup`
- `/run-checks`
- `/meditate <domain>`
- `/homeostasis <cycle-id|latest>`
- `/sleep <cycle-id|latest>`
- `/awaken <cycle-id|latest>`
- `/shadow`
- `/propose <change request>`
- `/queue`
- `/confirm <proposal-id>`
- `/process-queue`

Safe commands run directly.
High-impact evolution requests become proposals so Genie can keep moving without drifting when frontier access is scarce.
Confirmed low-risk proposals can be processed by a bounded workcell path that only auto-applies into generated docs/tests scopes.
Mind-cycle commands expose the unattended reflection -> meditation -> homeostasis -> sleep -> awakening loop without turning Telegram into raw shell access.

## Memory Layout

Canonical memory lives in:

- journal: `/local/state/genie/memory/journal.jsonl`
- semantic DB: `/local/state/genie/memory/memory.sqlite3`
- compatibility export: `/local/state/genie/memory/entries.jsonl`

Native projections live in:

- `/local/state/genie/memory/projections/IDENTITY.md`
- `/local/state/genie/memory/projections/USER.md`
- `/local/state/genie/memory/projections/MEMORY.md`
- `/local/state/genie/memory/projections/BOUNDARIES.md`
- `/local/state/genie/memory/projections/PROJECT_STATE.md`

## Provider State

Brain Router state lives in:

- `/local/state/genie/policy/provider-routing.env`
- `/local/state/genie/policy/provider-registry.json`
- `/local/state/genie/telemetry/provider-health.json`
- `/local/state/genie/telemetry/provider-benchmarks.json`

## Unattended Evolution

Genie now runs a bounded unattended inner loop:

- `reflection`
- `meditation`
- `homeostasis_review`
- `sleep`
- `awakening_verification`

Runtime artifacts live in:

- `/local/state/genie/runtime/mind-state.json`
- `/local/state/genie/runtime/mind-cycles.jsonl`
- `/local/state/genie/runtime/cycles`
- `/local/state/genie/runtime/checkpoints`
- `/local/state/genie/runtime/shadow-reports`

The root cron schedule now maintains:

- hourly and daily backups
- provider heartbeat, evaluation, scorecards, and discovery
- workcell queue processing
- unattended mind runs every 20 minutes
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
curl -s http://127.0.0.1:18790/state/domains
curl -s http://127.0.0.1:18790/state/summary
curl -s http://127.0.0.1:18790/state/stats
curl -s http://127.0.0.1:18790/memory/stats
curl -s http://127.0.0.1:18790/policy/summary
curl -s http://127.0.0.1:18790/gateway/summary
curl -s http://127.0.0.1:18790/telemetry/summary
curl -s http://127.0.0.1:18790/runtime/summary
```

Expected services:

- `genie-gateway`
- `genie-ethics`
- `genie-state`
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
- `GET /state/domains`
- `GET /state/summary`
- `GET /state/stats`
- `GET /memory/stats`
- `GET /policy/summary`
- `GET /gateway/summary`
- `GET /telemetry/summary`
- `GET /runtime/summary`
- `POST /state/ingest`
- `POST /state/search`
- `POST /state/context`
- `POST /state/sync-projections`
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
/local/state/genie/policy/genie-gateway.env
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
- state service data, including the memory journal and SQLite store
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
