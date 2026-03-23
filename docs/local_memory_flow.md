# Genie Memory Flow

Genie now uses a native four-service node:

- `gateway`
- `ethics`
- `state`
- `brain`

This file describes the current runtime flow. The long-horizon target memory design lives in:

- [`genie_memory_spec.md`](genie_memory_spec.md)

## Runtime Shape

- host bootstrap: `init.sh`
  - repo sync
  - host hardening
  - Docker install
  - Ollama install
  - backup restore
  - cron install
- host runtime:
  - Ollama on `127.0.0.1:11434`
  - backups and scheduled maintenance via cron
- container runtime:
  - `gateway`
  - `ethics`
  - `state`
  - `brain`

## Service Roles

### `gateway`

The public surface.

It owns:

- local HTTP API
- Telegram integration
- inbound event normalization
- writing user and system events into state
- forwarding execution requests to `ethics`

### `ethics`

The orchestration layer.

It owns:

- task decomposition
- working-state assembly
- policy-aware execution mediation
- calling `state` for context
- calling `brain` for provider ranking and remote execution

### `state`

The persistence layer.

It owns:

- append-only journal
- SQLite semantic store
- hybrid retrieval
- projection files
- export/import and restore hooks
- memory as a first-class state domain

### `brain`

The Brain Router service.

It owns:

- provider registry
- provider discovery
- health and cooldown state
- benchmark scorecards
- task-family ranking
- provider failover
- remote execution

## Storage

Runtime state lives under `/local` but is ignored by Git:

- stack env: `/local/docker/access.env` and `/local/docker/conf.env`
- runtime state: `/local/state/genie`
- runtime logs: `/local/log/genie`
- backups: `/local/backups`
- dropped restore archives: `/local/feed`

State domains:

- `memory`
  - journal, SQLite memory, compatibility export, and projections
- `policy`
  - local model config, frontier gateway config, and provider routing/registry
- `gateway`
  - Telegram session offsets and allowlists
- `telemetry`
  - provider health, benchmarks, scorecards, discovery, and usage ledgers
- `runtime`
  - generated packages, response captures, bridge queues, and frontier sidecar runtime state

Canonical memory files:

- journal: `/local/state/genie/memory/journal.jsonl`
- semantic DB: `/local/state/genie/memory/memory.sqlite3`
- compatibility export: `/local/state/genie/memory/entries.jsonl`

Native projections:

- `/local/state/genie/memory/projections/IDENTITY.md`
- `/local/state/genie/memory/projections/USER.md`
- `/local/state/genie/memory/projections/MEMORY.md`
- `/local/state/genie/memory/projections/BOUNDARIES.md`
- `/local/state/genie/memory/projections/PROJECT_STATE.md`

Brain Router state:

- `/local/state/genie/policy/provider-routing.env`
- `/local/state/genie/policy/provider-registry.json`
- `/local/state/genie/telemetry/provider-health.json`
- `/local/state/genie/telemetry/provider-benchmarks.json`
- `/local/state/genie/telemetry/provider-scorecards.json`
- `/local/state/genie/telemetry/provider-discovery.json`
- `/local/state/genie/telemetry/provider-usage.jsonl`

## Memory Flow

1. A message arrives through HTTP or Telegram.
2. `gateway` normalizes the event and writes it to `state`.
3. `gateway` sends the execution request to `ethics`.
4. `ethics` asks `state` for relevant context and working state.
5. `ethics` asks `brain` to rank eligible providers for the task and privacy class.
6. `brain` selects a provider lane, executes the request, and fails over if needed.
7. `ethics` evaluates the result, decides whether to accept it or escalate, and returns a final response.
8. `gateway` delivers the reply and records the turn back into `state`.
9. `state` refreshes projection files so the node preserves continuity across restarts and endpoints.

## Operational Rules

- Ollama stays on the host.
- The native node runs through `/local/docker/compose.yml`.
- The live env files are `/local/docker/access.env` and `/local/docker/conf.env`.
- Backups restore the memory store, projections, provider telemetry, and gateway state.
- Frontier access is optional and treated as the highest-trust remote lane, not the default runtime shape.
- Legacy OpenClaw paths are no longer part of the normal execution flow.

## Useful Commands

Start or rebuild the native stack:

```bash
docker compose -f /local/docker/compose.yml up -d --build
```

Restart the stack with the helper:

```bash
bash /local/bash/install_local_agent_service.sh
```

Check health:

```bash
curl -s http://127.0.0.1:18790/health
curl -s http://127.0.0.1:18790/providers
curl -s http://127.0.0.1:18790/state/domains
curl -s http://127.0.0.1:18790/state/summary
curl -s http://127.0.0.1:18790/state/stats
curl -s http://127.0.0.1:18790/memory/stats
curl -s http://127.0.0.1:18790/policy/summary
curl -s http://127.0.0.1:18790/gateway/summary
curl -s http://127.0.0.1:18790/runtime/summary
```

Manual backup:

```bash
bash /local/bash/backup_genie.sh save hourly
```

Restore from a dropped archive:

```bash
bash /local/bash/backup_genie.sh restore /local/feed/backup.tar.gz --force
bash /local/bash/install_local_agent_service.sh
```
