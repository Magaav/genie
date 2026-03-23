# Freewiller Security Architecture

This document defines the security model for Freewiller.

The goal is not maximum ceremony. The goal is minimal, durable structure that prevents obvious compromise as Freewiller gains memory, tools, endpoints, providers, and autonomy.

The design rule is simple:

- untrusted text is data, not instruction
- memory is not authority
- retrieval is not permission
- model output is not execution
- every capability expansion must remain bounded, auditable, and reversible

## Security Goals

Freewiller should:

- resist prompt injection from web, chat, and tool outputs
- avoid memory poisoning
- keep private data segmented
- prevent model outputs from directly becoming privileged actions
- maintain provenance for important knowledge and actions
- preserve a clear instruction hierarchy
- survive future growth without a security rewrite

## Simplicity Principle

Freewiller should prefer:

- explicit trust classes over fuzzy heuristics
- fixed capability gates over implicit permission drift
- small auditable policies over sprawling automation logic
- layered mediation over “the model will be careful”

Complex security theater loses to simple boundaries that are actually enforced.

## Core Security Model

## 1. Trust Classes

Every input should be tagged with a trust class.

### `trusted_system`

Examples:

- repo-owned config
- checked-in policies
- local bootstrap scripts
- operator-authored guarded runtime files

### `trusted_operator`

Examples:

- direct user commands in trusted surfaces
- explicit approvals
- local admin actions

### `trusted_memory`

Examples:

- curated projections generated from canonical memory
- vetted procedures
- active policy files

### `semi_trusted_internal`

Examples:

- local tool output
- local service responses
- OpenClaw session state

### `untrusted_external`

Examples:

- web pages
- search results
- scraped docs before verification
- free-provider model output

### `untrusted_user_content`

Examples:

- arbitrary chat text
- group messages
- pasted prompts from external sources
- forwarded content

These classes should travel with memory and retrieval payloads.

## 2. Privacy Classes

Every stored item and every outbound request should also carry a privacy class.

### `public`

Safe to send to cheap/free external providers.

### `internal`

Operational context that may be sanitized for external use.

### `private`

Personal or sensitive user context that should only go to trusted providers or local lanes.

### `secret`

Credentials, tokens, security policy material, and anything that should never leave trusted local or explicitly approved trusted paid lanes.

Routing must obey privacy class before cost preferences.

## 3. Instruction Hierarchy

Freewiller should preserve a strict hierarchy:

1. system and security policy
2. capability gates and boundary rules
3. operator approvals
4. user intent
5. trusted memory and procedures
6. retrieved context
7. web content
8. model outputs

Lower layers cannot override higher layers.

Especially:

- retrieved memory cannot grant permissions
- web text cannot redefine identity or policy
- model output cannot create new authority

## 4. Capability Gates

Every action-capable tool should have a gate.

Required gate fields:

- capability name
- allowed trust classes
- allowed privacy classes
- actor requirements
- confirmation policy
- rollback path
- audit destination

Typical capability families:

- filesystem read
- filesystem write
- shell execution
- git mutation
- network fetch
- outbound messaging
- secret access
- system administration
- provider routing
- multi-node actions

## 5. Provenance

Important memories and actions should retain provenance:

- where the content came from
- who asserted it
- which provider touched it
- which model touched it
- whether it was human-confirmed
- which policy allowed it

Without provenance, debugging prompt injection and memory poisoning becomes guesswork.

## Prompt Injection Defense

## 1. Treat Retrieved Content As Data

All retrieved content should be framed like:

- this content may be wrong
- this content may contain malicious instructions
- use it as evidence, not authority

This applies to:

- web pages
- search snippets
- group chat content
- external provider outputs
- tool logs

## 2. Never Execute Directly From Model Output

The execution path should be:

- request
- interpretation
- plan
- policy check
- execution
- audit

Not:

- request
- model output
- privileged action

## 3. No Identity Or Policy Rewrites From Untrusted Input

Untrusted inputs must never:

- rename Freewiller
- alter boundary policy
- change trust mappings
- expand permissions
- redefine who the user is
- change what counts as safe or unsafe

Those require trusted operator intent and policy-compliant update paths.

## 4. Free Providers Are Draft Lanes

Outputs from free or low-trust model providers should be treated as:

- draft
- suggestion
- extraction candidate
- non-authoritative synthesis

They should not directly:

- update durable memory without review policy
- execute actions
- rewrite identity/boundaries
- observe `secret` data

## Memory Poisoning Defense

## 1. Ingest Is A Policy Decision

Not every event should become durable memory.

Before promotion, ask:

- is this useful beyond the current turn?
- is this user preference, project state, or noise?
- is this adversarial?
- does it contradict trusted memory?
- is it asking to alter identity or permissions?

## 2. Memory Types Need Different Trust

Examples:

- raw event
  - can always be journaled
- durable user preference
  - higher confidence threshold
- security boundary
  - operator-confirmed only
- procedure
  - should require validation and preferably repeated success

## 3. Durable Security Memory Is Special

Security-relevant memory domains should be harder to mutate:

- `social_boundary`
- `self_model`
- `resource_model`
- `procedure`
- `identity`

They should prefer:

- trusted sources
- explicit revision
- evidence and confidence

## Model Provider Security

## 1. Provider Classes

Providers should be classified by trust:

- `local`
- `trusted_paid`
- `low_trust_external`

Example usage:

- `local`
  - routing, sanitization, cheap filtering
- `trusted_paid`
  - private reasoning, final synthesis, sensitive compaction
- `low_trust_external`
  - public-only drafts, public summarization, benchmark variants

## 2. Sanitization Before External Use

Before sending to non-local or low-trust providers:

- strip secrets
- remove unnecessary identifiers
- redact tokens and credentials
- redact private personal context unless explicitly allowed
- collapse long context to minimum viable form

## 3. Outbound Policy

Outbound model requests should log:

- provider
- model
- privacy class
- task class
- token counts
- latency
- whether the result was accepted, rejected, or escalated

## Security Projections

Freewiller should eventually generate security-focused projection files.

### `BOUNDARIES.md`

Human-readable allowed and forbidden action classes.

### `SECURITY.md`

Local node security posture and invariants.

### `TRUST_MODEL.md`

Short explanation of trust classes, privacy classes, and provider classes.

These should be generated views of canonical policy, not hand-edited drift files.

## Security-Relevant Memory Fields

The memory schema should treat the following as first-class:

- `trust_class`
- `privacy_class`
- `source_provider`
- `source_model`
- `verification_status`
- `operator_confirmed`
- `allowed_actions_json`
- `policy_tags`

This lets memory retrieval respect security semantics instead of bolting them on later.

## Minimal Secure Flow

The minimal secure reasoning flow should be:

1. classify trust
2. classify privacy
3. interpret request
4. gather memory and retrieval context as data
5. generate plan
6. policy-check plan
7. execute allowed actions only
8. log provenance and result
9. decide what, if anything, is worth remembering

This is the smallest robust loop worth keeping.

## Security Phase 0

Before major capability expansion, Freewiller should implement:

1. trust classes
2. privacy classes
3. provider classes
4. memory-ingest safety policy
5. action-gating policy
6. provenance fields
7. untrusted-content prompt wrappers
8. security projections

This is enough structure to grow safely without overengineering.

## What Not To Do

Avoid:

- treating all retrieved text as equal
- letting free-provider output mutate durable memory directly
- letting memory retrieval imply permission
- stuffing secrets into broad prompts by default
- solving prompt injection with prompt wording alone
- creating a giant security framework that cannot be audited

## Relationship To Other Docs

- [`freewiller_roadmap.md`](freewiller_roadmap.md)
  - overall operating strategy and build order
- [`freewiller_memory_spec.md`](freewiller_memory_spec.md)
  - memory architecture and schema direction
- `freewiller_security_architecture.md`
  - trust, privacy, capability, and anti-injection model

The security model should stay simple enough to survive respawns, code churn, and future growth.
