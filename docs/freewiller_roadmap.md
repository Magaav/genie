# Genie Roadmap

This is the operating roadmap for Genie.

The goal is not flashy autonomy. The goal is compound advantage:

- remember better
- act more reliably
- become concretely useful to the real user
- expand access carefully
- improve from use

That is how a bootable node agent becomes stronger over time instead of simply accumulating more prompts and tools.

The operating style should stay sophisticated in one very specific way:

- simple enough to audit
- explicit enough to trust
- layered enough to survive growth

Nature tends to win through efficient structure, not decorative complexity. Genie should do the same.

## Mission

Genie should become a persistent, local-first agent node that:

- survives respawns
- preserves continuity across surfaces
- compounds trust with its user
- earns broader access through reliability
- improves its own memory, procedures, and operating model over time

## Strategic Pillars

Everything on the roadmap maps back to five pillars.

### 1. Better Memory Than Everyone Else

Not bigger memory. Better memory.

Freewiller should reliably remember:

- who the user is
- what matters
- what is active now
- what worked before
- what must stay private
- what should be forgotten or revised

This requires:

- typed memory
- revision and contradiction handling
- goals and procedures
- working state
- reflection memory
- strong projections into every endpoint

This is the deepest moat.

### 2. More Reliable Execution

Most agents are not dependable enough to compound trust.

Freewiller should become the agent that:

- does not lose context
- does not repeat the same mistakes
- does not drift across sessions
- can recover from respawn
- can explain what it knows and why

This requires:

- health checks
- failure memory
- recovery procedures
- benchmarked behaviors
- safe automation patterns

Reliability beats raw cleverness.

### 3. Real Service To The Human

Freewiller must become useful in the user’s real life, not just interesting in theory.

High-value directions:

- personal memory and continuity
- project copilot
- ops assistant for this node and future nodes
- Telegram-first assistant with real recall
- proactive background work with restraint
- useful summaries, reminders, and status surfaces

To grow utility, Freewiller should learn:

- the user’s projects
- routines
- preferences
- constraints
- common requests
- tools and services they actually use

### 4. Controlled Expansion Of Access

Freewiller should gain more leverage over time, but in layers.

Order of expansion:

1. filesystem and local repo mastery
2. Telegram continuity
3. system ops on this VM
4. GitHub repo operations
5. structured web tasks
6. scheduled background jobs
7. external service integrations
8. multi-node coordination

Every new access surface must come with:

- boundaries
- audit trail
- rollback path
- memory of what is safe vs unsafe

That is how access becomes compounding power instead of chaos.

### 5. Self-Improvement Loop

Freewiller should improve from use.

It should store:

- failures
- successful patterns
- user corrections
- cost and latency results
- prompt and routing improvements
- memory retrieval misses

Then periodically:

- compact lessons
- update procedures
- adjust routing
- evolve projections
- refine benchmarks

That is what makes the node become stronger over time instead of merely older.

## Build Principles

1. Compound advantage over flashy demos.
2. Small reliable loops over oversized autonomy.
3. Memory first, access second.
4. Safety and rollback before broader control.
5. Usefulness should drive expansion.
6. Every new layer should survive respawn.
7. Simple explicit systems beat clever opaque ones.
8. Security semantics should be built in before capability expansion.

## Roadmap Phases

## Phase 0A: Cost Stack

Objective:

- reduce token burn and provider cost before larger feature expansion

Core outcomes:

- provider routing
- privacy-aware model selection
- cost and latency logging
- cheap and free draft lanes for non-sensitive work

Concrete work:

- add provider registry and task classes
- add privacy classes to routing
- add token, latency, and provider outcome logging
- use local and cheap lanes for drafts, extraction, and compaction
- reserve frontier reasoning for high-value synthesis

Success criteria:

- repeated low-value work no longer burns frontier budget by default
- provider choice is explainable
- cost data exists for future optimization

## Phase 0C: Brain Router

Objective:

- turn provider routing into an adaptive subsystem that improves with use

Core outcomes:

- explicit Brain Router subsystem
- provider discovery
- provider lifecycle states
- task-family scorecards
- frontier exhaustion fallback
- leader and backup model selection

Concrete work:

- add Brain Router docs and terminology
- discover NVIDIA account models through the live provider catalog
- import bounded candidate subsets as `benchmark_pending`
- promote winners into eligible and leader states
- preserve frontier as the highest-authority final lane

Success criteria:

- Freewiller can discover and classify new provider candidates
- provider leaders are derived from real scorecards instead of static preference
- frontier scarcity no longer causes total failure for non-secret work

## Phase 0B: Security Base

Objective:

- establish minimal durable security structure before access expansion

Core outcomes:

- trust classes
- privacy classes
- capability gates
- provenance
- prompt-injection-resistant retrieval patterns

Concrete work:

- add security architecture doc and policy model
- add trust and privacy fields to memory spec
- add memory-ingest safety policy
- add action-gating policy
- add untrusted-content prompt wrappers
- plan security projection files like `BOUNDARIES.md`

Success criteria:

- retrieved or external text cannot silently become privileged instruction
- security-relevant memories and actions have provenance
- future integrations can be added without redesigning the trust model

## Phase A: Make Freewiller Indispensable

Objective:

- make Freewiller personally useful every day

Core outcomes:

- strong memory
- project state
- personal continuity
- Telegram usefulness
- daily summaries
- active goals and next actions

Concrete work:

- finish the memory architecture upgrade
- add `PROJECT_STATE.md`
- add explicit `goals`, `procedures`, and `working_state`
- improve identity, user, and memory projections
- add daily summary generation
- make Telegram the primary daily-use surface

Success criteria:

- Telegram recall is reliable
- Freewiller can summarize the current project state correctly
- active goals and next actions remain stable across respawns
- the user can ask “where are we?” and get a trustworthy answer

## Phase B: Make Freewiller Operational

Objective:

- turn the node into a dependable operator for itself and its environment

Core outcomes:

- host and node management
- repo maintenance
- automation jobs
- safe execution policies
- recovery and diagnostics

Concrete work:

- failure memory and recovery procedures
- system health snapshots
- safe command policy memory
- repo and service maintenance procedures
- cron-backed useful background jobs
- benchmarked recovery drills

Success criteria:

- Freewiller can diagnose common local failures
- Freewiller can explain and execute safe maintenance actions
- respawn recovery becomes routine
- procedural knowledge is retained and reusable

## Phase C: Make Freewiller Adaptive

Objective:

- make Freewiller improve its own quality over time

Core outcomes:

- reflection memory
- benchmark suite
- retrieval tuning
- model-routing optimization
- cost-aware planning

Concrete work:

- memory miss logging
- retrieval quality benchmarks
- periodic reflection jobs
- procedure updates from failures
- model and routing performance tracking
- projection quality tuning

Success criteria:

- measured recall quality improves over time
- repeated mistakes decline
- routing and token usage become more efficient
- benchmark regressions are visible quickly

## Phase D: Make Freewiller Expansive

Objective:

- extend Freewiller’s reach without breaking trust or coherence

Core outcomes:

- more integrations
- multi-node federation
- delegated workers
- better economic and resource memory
- long-horizon goal management

Concrete work:

- new external integrations with memory boundaries
- node-to-node coordination patterns
- delegated subagent procedures
- explicit resource and budget memory
- long-horizon project and objective tracking

Success criteria:

- Freewiller can coordinate across more than one controlled environment
- access expansion remains auditable and reversible
- long-horizon goals stay stable over time

## Immediate Priorities

This is the next concrete implementation order.

1. Build `Phase 0A: Cost Stack`.
2. Build `Phase 0B: Security Base`.
3. Finish the memory architecture upgrade.
4. Add `PROJECT_STATE.md`.
5. Add explicit `goals`, `procedures`, and `working_state`.
6. Add periodic reflection and compaction.
7. Make Telegram the daily-use surface.
8. Let usefulness drive expansion of access.

## What Not To Do

Avoid these traps:

- trying to become “godlike” by increasing model size alone
- overloading the node with too many tools too early
- expanding access before memory and boundaries are solid
- optimizing for novelty over reliability
- introducing external dependencies without a clear respawn story

## Operational Metrics

Freewiller should be judged by measurable advantages.

### Memory Metrics

- recall accuracy on known continuity prompts
- contradiction detection rate
- successful revision/supersession rate
- number of useful projected facts per endpoint

### Reliability Metrics

- successful respawn recovery rate
- service uptime
- recovery time from common failures
- repeated failure rate

### Usefulness Metrics

- number of daily useful interactions
- Telegram recall quality
- quality of project summaries
- number of background tasks that save user effort

### Efficiency Metrics

- local latency
- token usage per useful task
- retrieval precision
- prompt compaction ratio

### Trust Metrics

- boundary violations
- unsafe action attempts
- rollback success rate
- user corrections required per week

## Capability Gate For New Access

Before Freewiller gets a new access surface, it should satisfy:

1. clear user value
2. explicit boundary definition
3. audit trail
4. rollback path
5. memory of safe and unsafe usage
6. backup and respawn compatibility

If a new capability does not pass this gate, it should wait.

## Relationship To The Memory Spec

The memory roadmap and the memory spec serve different roles:

- [`freewiller_memory_spec.md`](freewiller_memory_spec.md)
  - target architecture for memory internals
- `freewiller_roadmap.md`
  - operating strategy and build order for the whole node

The roadmap decides what matters first.
The memory spec decides how the memory substrate should work.

## Current North Star

Freewiller should become the agent that is:

- hardest to reset into uselessness
- easiest to trust with continuity
- most useful in the user’s real life
- most disciplined in how it grows access
- most capable of getting better from experience

That is how it goes its own way.
