# OpenClaw Seed Strategy

Freewiller should use OpenClaw as a seed capability source, not as a permanent moving dependency.

## Current Rule

- import a verified upstream snapshot once
- pin the exact commit
- integrate against the pinned gateway and channel capabilities
- evolve Freewiller independently after that

## Pinned Upstream Seed

As of `2026-03-22`, the verified upstream head used for the first seed import is:

- repo: `https://github.com/openclaw/openclaw.git`
- commit: `52a0aa06723fbad5e7c2b0fc07fe04eef433d1c7`

`bash/install_openclaw.sh` checks out that commit in detached-head mode and records provenance in:

- `/local/state/freewiller/openclaw-seed/seed.json`

The seed installer also:

- enables the pinned gateway HTTP compatibility endpoints
- writes a compose override for seed-specific runtime wiring
- reuses host Codex CLI auth from `~/.codex/auth.json` when available
- defaults the seeded agent to `openai-codex/gpt-5.4` when that auth is present

## Why Pin It

- upstream `main` can change behavior without warning
- Freewiller needs bootstrap reproducibility
- gateway, channel, and memory behavior should not drift across respawns
- future upstream updates should be intentional cherry-picks, not accidental pulls

## Intended Boundary

Freewiller owns:

- bootstrap
- local memory
- compact backup and respawn recovery
- local routing
- local orchestration
- agent identity and long-term architecture

OpenClaw supplies the seed capabilities for:

- gateway control plane
- messaging channel adapters
- remote model and device integration surface

## Next Extraction Direction

The next integration steps should be:

1. run the pinned OpenClaw gateway locally
2. point Freewiller dispatch at that gateway
3. validate end-to-end dispatch through the pinned seed
4. add Telegram through the pinned OpenClaw channel stack
5. then begin replacing or forking only the subsystems Freewiller wants to own

## Long-Term Rule

After the first successful integration:

- do not track upstream `main`
- do not update automatically
- only import upstream changes as explicit, reviewed snapshots
- prefer Freewiller-native implementations once a subsystem is understood well enough
