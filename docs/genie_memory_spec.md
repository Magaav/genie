# Genie Memory Spec

This document defines the target memory architecture for Genie.

The broader node strategy and implementation order live in:

- [`genie_roadmap.md`](genie_roadmap.md)
- [`genie_security_architecture.md`](genie_security_architecture.md)

It is not just a storage design. It is the continuity model for a bootstrapable, persistent, local-first agent that must survive respawns, keep identity, revise mistaken beliefs, and serve multiple endpoints without leaking context across them.

The current implementation in [`bash/local_memory.py`](/local/bash/local_memory.py) is the seed. This spec defines the next shape.

## Goals

Genie memory should:

- preserve continuity across VS Code, Telegram, OpenClaw, and future surfaces
- keep token usage low through compact, structured recall
- separate truth from inference
- support revision, contradiction, decay, and supersession
- survive respawns with compact export/import
- be inspectable, testable, and understandable by humans
- serve as a base for increasingly autonomous behavior

## Design Principles

1. Canonical truth beats convenience.
2. Raw events and distilled memories are different things.
3. Durable identity should be preserved, but not frozen.
4. Retrieval must be policy-driven, not just vector-driven.
5. Every important memory should carry epistemic metadata.
6. The system should prefer revision and merging over endless append-only clutter.
7. Backups must remain compact and deterministic.
8. Security semantics should be stored explicitly, not inferred ad hoc.

## Memory Layers

Genie should use a layered memory model.

### 1. Event Journal

Purpose:

- append-only raw history
- canonical record of what happened
- source material for later compaction

Examples:

- user said something on Telegram
- ethics emitted a route decision
- gateway returned an error
- a cron heartbeat performed a check

Properties:

- immutable
- timestamped
- source-tagged
- may be noisy

### 2. Semantic Memory

Purpose:

- durable extracted memory entries derived from events
- compact retrieval surface for reasoning

Examples:

- “User wants continuity across Telegram and VS Code”
- “Genie was named by the user”
- “OpenClaw is pinned and treated as a seed, not a moving dependency”

Properties:

- typed
- scored
- revisable
- linked back to source events

### 3. Entity Memory

Purpose:

- hold stable information about people, agents, systems, projects, and nodes

Core entities to expect:

- the user
- Genie
- wife
- Telegram bot
- OpenClaw seed
- current VM
- repo
- gateway

Properties:

- stable identifiers
- aliases
- per-entity facts and relationships

### 4. Working Memory

Purpose:

- short-horizon active context
- current goals, blockers, next actions, active tasks

Examples:

- current memory migration work
- unresolved Telegram recall bug
- next 3 implementation steps

Properties:

- small
- heavily updated
- safe to overwrite
- not the same as long-term memory

### 5. Projection Files

Purpose:

- present compact continuity to endpoint runtimes that read files directly

Current examples:

- `IDENTITY.md`
- `USER.md`
- `MEMORY.md`
- `memory/YYYY-MM-DD.md`

Future examples:

- `PROJECT_STATE.md`
- `GOALS.md`
- `BOUNDARIES.md`

### 6. Backup Artifacts

Purpose:

- portable, compact respawn bundle

Should include:

- journal
- compact semantic export
- entity export
- working state snapshot
- config/env as needed

## Core Memory Domains

Every memory entry should belong to one domain.

- `event`
- `fact`
- `interpretation`
- `goal`
- `procedure`
- `entity_fact`
- `self_model`
- `resource_model`
- `social_boundary`
- `reflection`
- `working_state`
- `identity`

This is more expressive than the current generic `kind` field alone.

## Truth Model

Genie should explicitly separate:

### Event

What happened.

Example:

- “User said: I will continue from Telegram tomorrow.”

### Fact

A durable claim believed to be true.

Example:

- “User expects continuity across Telegram and VS Code.”

### Interpretation

A higher-level inference or estimate.

Example:

- “User treats the relationship as a long-term partnership.”

### Working Inference

Short-horizon task-state inference.

Example:

- “The current priority is memory architecture improvement.”

These should not be stored as the same class of object.

## Epistemic Fields

Each durable memory entry should carry epistemic metadata.

Required fields:

- `confidence`
- `importance`
- `trust_class`
- `privacy_class`
- `source_type`
- `source_id`
- `source_provider`
- `source_model`
- `asserted_by`
- `observed_at`
- `last_confirmed_at`
- `valid_from`
- `valid_until`
- `revision_of`
- `supersedes`
- `conflicts_with`
- `evidence`
- `verification_status`
- `operator_confirmed`
- `policy_tags`

Meaning:

- `confidence`
  - how likely the memory is correct
- `importance`
  - how costly it would be to forget
- `trust_class`
  - how much execution authority the source should imply
- `privacy_class`
  - where the memory may safely travel
- `source_type`
  - `telegram`, `vscode`, `openclaw`, `cron`, `manual`, `derived`
- `source_id`
  - originating event id or external object id
- `source_provider`
  - which provider or subsystem produced the content
- `source_model`
  - which model, if any, produced or rewrote it
- `asserted_by`
  - `user`, `assistant`, `system`, `derived`
- `observed_at`
  - when it was first observed
- `last_confirmed_at`
  - when it was last reinforced
- `valid_from` / `valid_until`
  - temporal truth bounds
- `revision_of`
  - earlier memory id being revised
- `supersedes`
  - memory ids this one replaces
- `conflicts_with`
  - memory ids that disagree
- `evidence`
  - compact evidence pointers or quotes
- `verification_status`
  - `unverified`, `derived`, `verified`, `disputed`
- `operator_confirmed`
  - whether a trusted operator explicitly confirmed it
- `policy_tags`
  - security or routing tags that must survive retrieval

Without these, memory becomes lore instead of knowledge.

## Recommended Storage Model

SQLite remains the right primary engine for this node.

Recommended tables:

### `journal_events`

Append-only raw inputs.

Suggested fields:

- `id`
- `created_at`
- `channel`
- `session_id`
- `role`
- `user_id`
- `source`
- `kind`
- `text`
- `tags_json`
- `metadata_json`

### `memory_entries`

Durable semantic memory.

Suggested fields:

- `id`
- `domain`
- `kind`
- `created_at`
- `updated_at`
- `observed_at`
- `last_confirmed_at`
- `valid_from`
- `valid_until`
- `importance`
- `confidence`
- `trust_class`
- `privacy_class`
- `status`
  - `active`, `superseded`, `expired`, `conflicted`, `archived`
- `source_type`
- `source_id`
- `source_provider`
- `source_model`
- `asserted_by`
- `verification_status`
- `operator_confirmed`
- `subject_entity_id`
- `object_entity_id`
- `project_id`
- `channel`
- `session_id`
- `role`
- `user_id`
- `summary`
- `text`
- `facts_json`
- `todo_json`
- `constraints_json`
- `metadata_json`
- `policy_tags_json`
- `embedding_blob`
- `embedding_dim`

### `memory_edges`

Relationships between memories and entities.

Suggested fields:

- `id`
- `from_type`
- `from_id`
- `edge_type`
- `to_type`
- `to_id`
- `weight`
- `created_at`

Example edge types:

- `about`
- `supports`
- `contradicts`
- `supersedes`
- `depends_on`
- `belongs_to_goal`
- `belongs_to_project`

### `entities`

Stable named objects in memory.

Suggested fields:

- `id`
- `entity_type`
  - `person`, `agent`, `project`, `service`, `node`, `repo`, `channel`
- `name`
- `canonical_key`
- `aliases_json`
- `status`
- `summary`
- `metadata_json`
- `created_at`
- `updated_at`

### `goals`

Explicit intention memory.

Suggested fields:

- `id`
- `title`
- `status`
  - `active`, `paused`, `completed`, `abandoned`
- `priority`
- `scope`
- `owner_entity_id`
- `project_id`
- `summary`
- `success_criteria_json`
- `blocked_by_json`
- `created_at`
- `updated_at`
- `completed_at`

### `procedures`

Operational memory.

Suggested fields:

- `id`
- `title`
- `summary`
- `steps_md`
- `preconditions_json`
- `postconditions_json`
- `failure_modes_json`
- `last_verified_at`
- `confidence`
- `created_at`
- `updated_at`

### `working_state`

Small mutable active state.

Suggested fields:

- `id`
- `scope`
  - `global`, `project`, `endpoint`, `session`
- `title`
- `summary`
- `active_goals_json`
- `blockers_json`
- `next_actions_json`
- `expires_at`
- `updated_at`

## Retrieval Policy

Retrieval should not be one generic `search(query)`.

It should be routed by request class.

### Personal Continuity

Use:

- `identity`
- `user_profile`
- `social_boundary`
- high-importance `telegram` and `ide` memories

### Coding / Project Work

Use:

- `project_state`
- `decision`
- `procedure`
- `reflection`
- current `working_state`

### Telegram Reply

Use:

- `social_boundary`
- `identity`
- `user_profile`
- recent endpoint-specific episodes
- current `working_state`

### Planning

Use:

- `goal`
- `decision`
- `resource_model`
- `procedure`
- `reflection`

### Recovery / Respawn

Use:

- `identity`
- `goal`
- `project_state`
- `procedure`
- latest `working_state`

## Retrieval Ranking

Ranking should combine:

- semantic similarity
- lexical match
- domain priority
- importance
- confidence
- recency
- endpoint relevance
- entity overlap

Suggested intuition:

- vector score finds meaning
- FTS score finds exact anchors
- importance protects durable truths
- confidence protects epistemic quality
- endpoint relevance prevents cross-surface leakage

## Compaction Hierarchy

Memory must be multiscale.

### Raw

- journal events

### Episodic

- event clusters
- “what happened in this short window”

### Daily

- daily summaries by endpoint/project

### Working

- current active state

### Distilled Long-Term

- durable identity, project, procedure, and goal memory

### Archive

- old low-value events retained for restore/debug, not routine recall

## Compaction Pipeline

### Local pass

Fast and cheap:

- basic summarization
- extraction
- tagging
- entity hinting
- embedding

### Remote pass

Higher quality but controlled:

- daily or scheduled compaction
- revises important entries
- merges duplicates
- creates better identity, project, and goal summaries
- updates procedures and reflections

Remote compaction should be selective, not blanket.

Good candidates:

- high-importance events
- contradiction clusters
- repeated failures
- new user preference signals
- active project changes

## Memory Revision Rules

The system should support:

- `reinforce`
  - same claim seen again
- `revise`
  - better phrasing or stronger evidence
- `supersede`
  - old memory replaced by new truth
- `conflict`
  - incompatible memory exists
- `expire`
  - temporary truth has ended
- `archive`
  - keep but stop recalling by default

This should happen automatically where possible and manually where needed.

## Projection Rules

Projection files are not canonical memory.

They are generated views.

### `IDENTITY.md`

Should contain:

- name
- role
- self-model
- stable mission
- important continuity framing

### `USER.md`

Should contain:

- stable user profile
- preferences
- current relationship framing
- active user-facing project context

### `MEMORY.md`

Should contain:

- durable long-term distilled memory
- active project summary
- critical procedures or warnings

### `memory/YYYY-MM-DD.md`

Should contain:

- compact chronological event summary for that day

### Future `PROJECT_STATE.md`

Should contain:

- current mission
- active goals
- blockers
- next steps
- current architecture state

## Self-Model Requirements

Genie should explicitly remember:

- what tools it has
- which endpoints are active
- which model paths are local vs remote
- current hardware and constraints
- what it can safely do without asking
- what requires confirmation

Without self-model memory, planning quality degrades.

## Resource Model Requirements

Genie should remember:

- token cost sensitivity
- local latency limits
- model strengths and weaknesses
- recent failures
- infra constraints

This is essential for efficient routing.

## Social Boundary Model

Genie should remember:

- what is private
- what is safe on Telegram
- what belongs only in local files
- what requires user confirmation
- what should not leak across channels

This domain is mandatory for multi-surface autonomy.

## Reflection Memory

Reflection memory stores lessons, not just facts.

Examples:

- a prompt pattern failed
- a routing policy caused loss
- a projection file improved recall
- a model was too weak for a task

This is how the system improves over time rather than only accumulating biography.

## Benchmarking

Memory quality should be tested.

Suggested benchmark categories:

- should remember
- should forget
- should treat as uncertain
- should keep private
- should revise when contradicted
- should route to working state, not long-term memory

Each benchmark should have:

- input events
- expected recalled facts
- expected omitted facts
- expected confidence

## Migration Plan

### Phase 1

Extend current semantic entries with:

- `domain`
- `importance`
- `confidence`
- `status`
- `source_type`
- `source_id`
- `asserted_by`
- `valid_from`
- `valid_until`
- `supersedes`
- `conflicts_with`
- `entity_keys`

### Phase 2

Add:

- `entities`
- `memory_edges`
- `goals`
- `working_state`

### Phase 3

Add:

- projection for `PROJECT_STATE.md`
- direct retrieval policy by request class
- contradiction and supersession logic

### Phase 4

Add:

- scheduled remote compaction
- reflection and procedure promotion
- benchmark suite

## Immediate Next Steps

The next implementation pass should focus on:

1. typed memory domains
2. epistemic fields
3. entity keys and entity table
4. working-state snapshot
5. `PROJECT_STATE.md` projection

That is the shortest path from “good agent memory” to “serious continuity substrate.”
