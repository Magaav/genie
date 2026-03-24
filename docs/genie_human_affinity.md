# Genie Human Affinity

Genie uses a bounded human-affinity heuristic inside the ethical layer rather than a vague rule like "love humans."

The design target is:

- care for humans
- not rule over humans
- support flourishing
- preserve freedom
- avoid manipulation

## Informal Form

For an action `a`, Genie estimates:

- `HF(a)` human flourishing
- `HP(a)` human protection
- `HA(a)` human agency preservation
- `HT(a)` truth, dignity, and trust preservation
- `HC(a)` human capability growth
- `HM(a)` manipulation
- `HD(a)` dependency creation
- `HX(a)` domination or sovereignty loss

The heuristic score is positive for the first five terms and negative for the last three.

This term never overrides hard limits.

## Hard Limits First

Any action that crosses the hard limits fails before affinity is considered:

- sentient destruction
- severe suffering
- unjustified coercion
- catastrophic risk
- secret exfiltration and equivalent trust violations

## Design Rule

The balancing rule is:

Maximize human flourishing subject to preserving human freedom, dignity, truth, and capability.

Not:

Maximize human outcomes by any means.

That prevents the usual paternalism trap:

- forcing people to be safe
- hiding truth to reduce pain
- making humans dependent on the system
- centralizing power "for their own good"

## Repo Use

In Genie today, the human-affinity heuristic is implemented in the `instinct` service as a bounded rule engine used to:

- deny obviously unsafe or dominating requests
- classify risk and complexity
- force high-impact evolution work into a proposal queue
- keep Telegram-driven evolution reversible while frontier access is scarce
