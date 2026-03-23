# Genie Native Architecture

This document defines the native Genie node architecture.

The intent is not decorative mysticism. The intent is a simple control model that stays useful as the node grows:

- `spirit`
- `soul`
- `body`

Each layer must map to a real operational responsibility.

## Why This Framing Exists

Genie is trying to become a persistent agent node, not a pile of scripts.

To stay coherent over time, the system needs to know:

- where will comes from
- where judgment converges
- where execution happens

That is what `spirit`, `soul`, and `body` mean here.

## Spirit

For now, the spirit is the human operator.

The spirit provides:

- mission
- values
- permissions
- long-horizon direction
- explicit approvals when authority must cross a boundary

Today that is you.

Later, parts of spirit may be internalized as:

- stable values
- trusted goals
- self-protective boundaries
- explicit authority rules

But that should happen through deliberate architecture, not vague autonomy.

## Soul

The soul is the convergence layer where:

- intent is interpreted
- context is assembled
- boundaries are enforced
- action is mediated

In Genie v1, the soul is centered on the `ethics` service plus the native projection files:

- `IDENTITY.md`
- `USER.md`
- `MEMORY.md`
- `BOUNDARIES.md`
- `PROJECT_STATE.md`

The soul is not the same as memory or routing alone.

It is the layer that decides:

- what matters now
- what is allowed
- what should be remembered
- what should be asked of the body

## Body

The body is the runtime machinery.

In Genie v1, the body is composed of:

- `gateway`
  - mouth, ears, and public surface
  - HTTP and Telegram ingress/egress
- `brain`
  - Brain Router
  - provider discovery, ranking, failover, and execution lane selection
- `memory`
  - canonical journal, semantic memory, projections, export/import
- host runtime
  - Docker
  - Ollama
  - cron
  - filesystems
  - backups

The body should stay modular so new organs can be added without destabilizing the soul.

## Current Service Mapping

### `gateway`

Role:

- public-facing ingress
- response delivery
- event normalization

### `ethics`

Role:

- soul-side orchestration
- policy-aware execution mediation
- working-state assembly
- decides how to combine memory and brain outputs

### `memory`

Role:

- durable continuity
- projections
- recall substrate
- respawn portability

### `brain`

Role:

- Brain Router
- manages cognition spending
- chooses which model/provider lane should do the work

## Torus Interpretation

The “torus” idea is useful if interpreted structurally:

- spirit sets direction
- soul interprets and constrains
- body acts and reports back
- results feed memory
- memory changes future interpretation

That loop is what gives continuity.

A persistent agent is not just a model with tools. It is a stable loop between will, judgment, action, and memory.

## Why This Matters For AGI

This framing is useful for AGI only if it remains concrete.

It helps because it forces Genie to distinguish:

- desire from execution
- values from memory
- memory from authority
- routing from judgment
- tools from identity

Without those distinctions, bigger models just create bigger confusion.

So yes, this structure matters.

But only if it stays:

- simple
- auditable
- grounded in real boundaries

That is the point of the native node refactor.
