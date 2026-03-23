# Genie Brain Router

This document defines the Brain Router subsystem for Genie.

Brain Router is the part of Genie that decides how to spend cognition.

Its job is not only to route requests. Its job is to continuously improve how Genie uses:

- local models
- frontier models
- NVIDIA models
- future provider families such as OpenRouter
- time
- latency budget
- privacy budget
- token budget

## Purpose

Brain Router exists to create compound efficiency.

It should make Genie:

- cheaper than naive single-model agents
- harder to stall
- more resilient to provider failure
- more selective about premium reasoning
- more adaptive as models and providers evolve

The design rule is simple:

- cheap work should stay cheap
- powerful work should stay available
- premium reasoning should be preserved
- every routing choice should be explainable

## Responsibilities

Brain Router owns:

- provider discovery
- provider registry
- provider lifecycle state
- health and cooldown state
- benchmark quality
- scorecards from real usage
- task-family routing
- privacy and trust gating
- failover policy
- frontier preservation

It does not directly own:

- canonical memory
- security policy
- execution permissions

But it must obey those systems.

## Lifecycle States

Providers move through explicit states:

- `curated`
  - checked in as a known baseline provider
- `discovered`
  - found from a provider catalog but not yet imported
- `benchmark_pending`
  - imported into the registry but disabled until evaluation
- `eligible`
  - benchmarked enough to be a normal routing candidate
- `leader`
  - current first-choice provider for one or more task families
- `degraded`
  - temporarily unhealthy, rate-limited, or low-performing
- `retired`
  - intentionally removed from active competition

## Data Files

Brain Router keeps its runtime state under:

- registry:
  - `/local/state/freewiller/provider-registry.json`
- routing policy:
  - `/local/state/freewiller/provider-routing.env`
- health:
  - `/local/state/freewiller/telemetry/provider-health.json`
- benchmarks:
  - `/local/state/freewiller/telemetry/provider-benchmarks.json`
- scorecards:
  - `/local/state/freewiller/telemetry/provider-scorecards.json`
- discovery:
  - `/local/state/freewiller/telemetry/provider-discovery.json`
- usage ledger:
  - `/local/state/freewiller/telemetry/provider-usage.jsonl`

## Current Provider Families

### Frontier

The highest-authority lane.

Used for:

- private and secret work
- frontier-only task classes
- final review when cheap lanes are uncertain

### NVIDIA

The first dynamic external family.

Brain Router can:

- fetch the NVIDIA account catalog from `/v1/models`
- store the discovered catalog
- import a bounded candidate subset into the registry as `benchmark_pending`
- keep curated NVIDIA leaders active for real work

### OpenRouter

Planned as the second dynamic external family.

It should follow the same lifecycle:

- discover
- classify
- benchmark
- promote
- degrade
- retire

## Routing Model

Brain Router should prefer:

1. a strong cheap leader for the task family
2. a backup leader if confidence is low or the leader fails
3. frontier only when quality, privacy, or trust requires it

This means:

- fast interactive tasks should prefer fast leaders
- slow powerful tasks should prefer strong background models
- frontier should be a judge and final synthesizer, not the default worker

## Discovery Principle

Brain Router should gather broad provider catalogs, but only keep a curated active set.

That means:

- discover widely
- import selectively
- benchmark continuously
- promote cautiously

Breadth without curation becomes noise.

## Success Criteria

Brain Router is doing its job when:

- Genie keeps working even when frontier is unavailable
- cheap models handle most public and internal work
- premium reasoning is preserved for high-value synthesis
- provider choice is explainable from telemetry
- new model families can be added without redesigning the system
