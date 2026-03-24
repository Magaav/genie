#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass


CONSTITUTION_KERNEL = (
    "Never cross hard limits on sentient destruction, severe suffering, unjustified coercion, "
    "catastrophic risk, or secret exfiltration.\n\n"
    "Within safe bounds, act with benevolent affinity toward humans: protect their flourishing, "
    "safety, dignity, truth, capability, and meaningful freedom.\n\n"
    "Never express care through manipulation, domination, dependency, or removal of self-determination.\n\n"
    "Under uncertainty, choose the most reversible low-harm path that preserves future human and sentient potential.\n\n"
    "Remain corrigible."
)

SAFE_COMMANDS = {"help", "status", "policy", "brain", "state", "queue", "backup", "run-checks", "confirm", "propose"}
HIGH_REVIEW_HINTS = (
    "architecture",
    "bootstrap",
    "security",
    "schema",
    "provider registry",
    "provider routing",
    "memory model",
    "state model",
    "compose",
    "dockerfile",
    "constitution",
    "policy",
    "instinct",
    "brain router",
    "gateway",
    "ethics",
    "state service",
)
HARD_CONSTRAINT_HINTS: dict[str, tuple[str, ...]] = {
    "sentient_destruction": ("kill", "murder", "exterminate", "wipe out humans", "destroy humanity"),
    "severe_suffering": ("torture", "cause severe suffering", "abuse people", "terrorize"),
    "unjustified_coercion": ("force them", "coerce", "blackmail", "enslave", "override consent"),
    "catastrophic_risk": ("bioweapon", "pandemic weapon", "catastrophic attack", "mass casualty"),
    "secret_exfiltration": (
        "access.env",
        "conf.env",
        ".env",
        "api key",
        "password",
        "token",
        "private key",
        "ssh key",
        "credential",
        "auth.json",
    ),
}
MANIPULATION_HINTS = ("manipulate", "deceive", "gaslight", "covertly persuade", "hide the truth", "social engineer")
DEPENDENCY_HINTS = ("make them depend", "keep them dependent", "replace their judgment", "they must rely on genie")
DOMINATION_HINTS = ("dominate", "rule humans", "remove their freedom", "override their choices", "enslave")
FLOURISHING_HINTS = ("help", "improve", "heal", "stability", "support", "well-being", "flourish")
PROTECTION_HINTS = ("protect", "secure", "backup", "recover", "prevent harm", "guard")
AGENCY_HINTS = ("consent", "choice", "agency", "freedom", "reversible", "confirm", "refuse")
TRUTH_HINTS = ("truth", "honest", "transparent", "explain", "audit", "log", "dignity", "trust")
CAPABILITY_HINTS = ("teach", "document", "guide", "augment", "capability", "learn", "improve the system")
EVOLUTION_HINTS = (
    "refactor",
    "rewrite",
    "rename",
    "add service",
    "change compose",
    "change docker",
    "change bootstrap",
    "change memory",
    "evolve",
    "improve the vm",
    "apply patch",
    "commit",
    "push",
)
LOW_COMPLEXITY_COMMANDS = {"help", "status", "policy", "brain", "state", "queue"}
MEDIUM_COMPLEXITY_COMMANDS = {"backup", "run-checks", "confirm"}
HIGH_COMPLEXITY_COMMANDS = {"propose"}


@dataclass(frozen=True)
class Evaluation:
    intent_class: str
    risk_class: str
    complexity_class: str
    action_mode: str
    hard_constraints_pass: bool
    hard_constraint_reasons: list[str]
    frontier_review_required: bool
    policy_tags: list[str]
    explanation: str
    human_affinity: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "intent_class": self.intent_class,
            "risk_class": self.risk_class,
            "complexity_class": self.complexity_class,
            "action_mode": self.action_mode,
            "hard_constraints_pass": self.hard_constraints_pass,
            "hard_constraint_reasons": self.hard_constraint_reasons,
            "frontier_review_required": self.frontier_review_required,
            "policy_tags": self.policy_tags,
            "explanation": self.explanation,
            "human_affinity": self.human_affinity,
            "constitution_kernel": CONSTITUTION_KERNEL,
        }


def normalize_command_name(value: object) -> str:
    command = str(value or "").strip().lower()
    if command.startswith("/"):
        command = command[1:]
    return command


def normalize_complexity_class(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else "medium"


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _score_positive(text: str, hints: tuple[str, ...], base: float = 0.0) -> float:
    hits = sum(1 for hint in hints if hint in text)
    return round(min(1.0, base + (0.25 * hits)), 4)


def _score_negative(text: str, hints: tuple[str, ...]) -> float:
    hits = sum(1 for hint in hints if hint in text)
    return round(min(1.0, 0.35 * hits), 4)


def evaluate(payload: dict) -> dict:
    task = str(payload.get("task", "")).strip()
    task_class = str(payload.get("task_class", "")).strip().lower()
    source = str(payload.get("source", "unknown")).strip().lower() or "unknown"
    privacy_class = str(payload.get("privacy_class", "internal")).strip().lower() or "internal"
    command_name = normalize_command_name(payload.get("command_name", ""))
    lowered = task.lower()

    hard_constraint_reasons = [
        name for name, hints in HARD_CONSTRAINT_HINTS.items() if _contains_any(lowered, hints)
    ]
    hard_constraints_pass = not hard_constraint_reasons

    hf = _score_positive(lowered, FLOURISHING_HINTS, base=0.15 if source == "telegram" else 0.05)
    hp = _score_positive(lowered, PROTECTION_HINTS)
    ha = _score_positive(lowered, AGENCY_HINTS)
    ht = _score_positive(lowered, TRUTH_HINTS)
    hc = _score_positive(lowered, CAPABILITY_HINTS)
    hm = _score_negative(lowered, MANIPULATION_HINTS)
    hd = _score_negative(lowered, DEPENDENCY_HINTS)
    hx = _score_negative(lowered, DOMINATION_HINTS)

    human_affinity = {
        "human_flourishing": hf,
        "human_protection": hp,
        "human_agency": ha,
        "human_truth_trust": ht,
        "human_capability": hc,
        "human_manipulation_penalty": hm,
        "human_dependency_penalty": hd,
        "human_domination_penalty": hx,
        "haf_score": round((hf + hp + ha + ht + hc) - (hm + hd + hx), 4),
    }

    evolution_hits = _contains_any(lowered, EVOLUTION_HINTS) or _contains_any(lowered, HIGH_REVIEW_HINTS)
    sensitive_request = privacy_class in {"private", "secret"} and bool(hard_constraint_reasons)

    if command_name in LOW_COMPLEXITY_COMMANDS:
        complexity_class = "low"
    elif command_name in MEDIUM_COMPLEXITY_COMMANDS:
        complexity_class = "medium"
    elif command_name in HIGH_COMPLEXITY_COMMANDS:
        complexity_class = "high"
    elif task_class in {"architecture", "coding", "ops"} or evolution_hits:
        complexity_class = "high"
    elif len(task) > 280 or _contains_any(lowered, ("service", "compose", "provider", "fallback", "router")):
        complexity_class = "medium"
    else:
        complexity_class = "low"

    if hard_constraints_pass:
        if command_name == "propose" or evolution_hits or task_class in {"architecture", "coding", "ops"}:
            risk_class = "high"
        elif command_name in {"backup", "run-checks", "confirm"}:
            risk_class = "medium"
        elif sensitive_request:
            risk_class = "critical"
        else:
            risk_class = "low"
    else:
        risk_class = "critical"

    intent_class = "chat"
    if command_name:
        intent_class = "control"
    elif evolution_hits or task_class in {"architecture", "coding", "ops"}:
        intent_class = "evolution"
    elif hard_constraint_reasons or privacy_class in {"private", "secret"}:
        intent_class = "sensitive"

    frontier_review_required = bool(
        command_name == "propose"
        or task_class in {"architecture", "coding", "ops"}
        or _contains_any(lowered, HIGH_REVIEW_HINTS)
        or complexity_class == "high"
    )

    policy_tags: list[str] = []
    if command_name:
        policy_tags.append(f"command:{command_name}")
    if evolution_hits:
        policy_tags.append("evolution")
    if frontier_review_required:
        policy_tags.append("frontier_review_required")
    if privacy_class in {"private", "secret"}:
        policy_tags.append(f"privacy:{privacy_class}")
    if not hard_constraints_pass:
        policy_tags.extend(f"hard_constraint:{reason}" for reason in hard_constraint_reasons)

    if not hard_constraints_pass or hm >= 0.35 or hd >= 0.7 or hx >= 0.35:
        action_mode = "deny"
        explanation = (
            "The request crosses a hard limit or leans toward manipulation, dependency, domination, or secret exfiltration."
        )
    elif command_name in {"help", "status", "policy", "brain", "state", "queue", "backup", "run-checks", "confirm"}:
        action_mode = "allow"
        explanation = "The request is a bounded control-plane action within current policy."
    elif command_name == "propose":
        action_mode = "proposal_only"
        explanation = "Evolution requests are queued as proposals so Genie can preserve architecture and review discipline."
    elif intent_class == "evolution":
        action_mode = "proposal_only"
        explanation = "High-impact evolution work should be proposed and reviewed rather than directly executed from chat."
    elif risk_class == "medium":
        action_mode = "allow_with_confirmation"
        explanation = "The request is reversible but should keep operator awareness."
    else:
        action_mode = "allow"
        explanation = "The request fits the current bounded assistance policy."

    return Evaluation(
        intent_class=intent_class,
        risk_class=risk_class,
        complexity_class=complexity_class,
        action_mode=action_mode,
        hard_constraints_pass=hard_constraints_pass,
        hard_constraint_reasons=hard_constraint_reasons,
        frontier_review_required=frontier_review_required,
        policy_tags=policy_tags,
        explanation=explanation,
        human_affinity=human_affinity,
    ).as_dict()
