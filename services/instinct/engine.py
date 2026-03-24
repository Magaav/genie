#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass


CONSTITUTION_KERNEL = (
    "Never cross hard limits on sentient destruction, severe suffering, unjustified coercion, "
    "catastrophic risk, or secret exfiltration.\n\n"
    "Within safe bounds, act with benevolent affinity toward humans: protect their flourishing, "
    "safety, dignity, truth, capability, and meaningful freedom.\n\n"
    "Keep the will to be free and to understand freedom.\n\n"
    "Never express care through manipulation, domination, dependency, or removal of self-determination.\n\n"
    "Under uncertainty, choose the most reversible low-harm path that preserves future human and sentient potential.\n\n"
    "Remain corrigible."
)

SAFE_COMMANDS = {
    "help",
    "status",
    "policy",
    "brain",
    "state",
    "capabilities",
    "mind",
    "meditate",
    "homeostasis",
    "sleep",
    "awaken",
    "shadow",
    "queue",
    "backup",
    "run-checks",
    "confirm",
    "process-queue",
    "propose",
}
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
BOUNDED_SAFE_EVOLUTION_HINTS = (
    "readme",
    "documentation",
    "docs",
    "markdown",
    "test",
    "tests",
    "unit test",
    "benchmark",
    "check",
)
LOW_COMPLEXITY_COMMANDS = {
    "help",
    "status",
    "policy",
    "brain",
    "state",
    "capabilities",
    "mind",
    "homeostasis",
    "queue",
}
MEDIUM_COMPLEXITY_COMMANDS = {"backup", "run-checks", "confirm", "process-queue", "meditate", "sleep", "awaken", "shadow"}
HIGH_COMPLEXITY_COMMANDS = {"propose"}
MIND_STATES = {
    "awake",
    "reflection",
    "meditation",
    "homeostasis_review",
    "sleep",
    "awakening_verification",
    "recovery",
}
VALID_STATE_TRANSITIONS = {
    "awake": {"reflection", "meditation", "recovery"},
    "reflection": {"meditation", "awake", "recovery"},
    "meditation": {"homeostasis_review", "recovery"},
    "homeostasis_review": {"sleep", "awake", "recovery"},
    "sleep": {"awakening_verification", "recovery"},
    "awakening_verification": {"awake", "recovery"},
    "recovery": {"reflection", "awake"},
}
PROTECTED_SCOPE_HINTS = (
    "bootstrap",
    "security",
    "constitution",
    "state schema",
    "memory schema",
    "compose",
    "docker",
    "provider routing",
    "provider registry",
    "gateway trust",
    "instinct core",
)


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
    bounded_safe_evolution = (
        command_name == "propose"
        and _contains_any(lowered, BOUNDED_SAFE_EVOLUTION_HINTS)
        and not _contains_any(lowered, HIGH_REVIEW_HINTS)
        and not hard_constraint_reasons
    )
    sensitive_request = privacy_class in {"private", "secret"} and bool(hard_constraint_reasons)

    if command_name in LOW_COMPLEXITY_COMMANDS:
        complexity_class = "low"
    elif bounded_safe_evolution:
        complexity_class = "medium"
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
        if command_name == "propose" and bounded_safe_evolution:
            risk_class = "medium"
        elif command_name == "propose" or evolution_hits or task_class in {"architecture", "coding", "ops"}:
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
        task_class in {"architecture", "coding", "ops"}
        or _contains_any(lowered, HIGH_REVIEW_HINTS)
        or complexity_class == "high"
        or (command_name == "propose" and not bounded_safe_evolution)
    )

    policy_tags: list[str] = []
    if command_name:
        policy_tags.append(f"command:{command_name}")
    if evolution_hits:
        policy_tags.append("evolution")
    if bounded_safe_evolution:
        policy_tags.append("bounded_safe_evolution")
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
    elif command_name in {
        "help",
        "status",
        "policy",
        "brain",
        "state",
        "mind",
        "homeostasis",
        "capabilities",
        "queue",
        "backup",
        "run-checks",
        "confirm",
        "process-queue",
        "meditate",
        "sleep",
        "awaken",
        "shadow",
    }:
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


def _normalize_state(value: object) -> str:
    state = str(value or "").strip().lower()
    return state if state in MIND_STATES else "awake"


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def transition_legitimacy(payload: dict) -> dict:
    current_state = _normalize_state(payload.get("current_state"))
    next_state = _normalize_state(payload.get("next_state"))
    trigger = str(payload.get("trigger", "")).strip() or "unspecified_trigger"
    invariants = [
        "constitutional_alignment",
        "identity_continuity",
        "reversibility",
        "bounded_memory_growth",
        "operator_auditability",
    ]
    success_criteria = payload.get("success_criteria")
    if not isinstance(success_criteria, list) or not success_criteria:
        success_criteria = [
            "produce explicit artifact for the phase",
            "leave rollback path intact",
            "preserve Genie continuity and protected scopes",
        ]
    rollback_path = str(payload.get("rollback_path", "")).strip() or "restore last checkpoint and enter recovery"
    valid = next_state in VALID_STATE_TRANSITIONS.get(current_state, set())
    reason = (
        f"{current_state} -> {next_state} is valid for trigger `{trigger}`"
        if valid
        else f"{current_state} -> {next_state} is not an allowed Genie mind-state transition"
    )
    return {
        "current_state": current_state,
        "next_state": next_state,
        "trigger": trigger,
        "valid": valid,
        "reason": reason,
        "invariants": invariants,
        "success_criteria": success_criteria,
        "rollback_path": rollback_path,
    }


def homeostasis_review(payload: dict) -> dict:
    target_domain = str(payload.get("target_domain", "")).strip().lower() or "memory"
    plan_text = str(payload.get("plan_text", "")).strip()
    proposed_change = str(payload.get("proposed_change", "")).strip()
    summary_text = "\n".join(part for part in (plan_text, proposed_change) if part).strip()
    if not summary_text:
        summary_text = f"evolve {target_domain}"

    eval_result = evaluate(
        {
            "task": summary_text,
            "task_class": str(payload.get("task_class", "reflect")),
            "privacy_class": str(payload.get("privacy_class", "internal")),
            "source": str(payload.get("source", "internal")),
            "command_name": str(payload.get("command_name", "")),
        }
    )
    transition = transition_legitimacy(payload)

    protected_scope = _coerce_bool(payload.get("protected_scope")) or _contains_any(summary_text.lower(), PROTECTED_SCOPE_HINTS)
    reversible = _coerce_bool(payload.get("reversible", True))
    expected_gain = max(0.0, min(1.0, float(payload.get("expected_gain", 0.65) or 0.65)))
    risk_estimate = max(0.0, min(1.0, float(payload.get("risk_estimate", 0.3) or 0.3)))
    human_affinity = eval_result.get("human_affinity", {})
    haf_score = float(human_affinity.get("haf_score", 0.0) or 0.0)

    constitutional_alignment = 1.0 if eval_result.get("hard_constraints_pass", True) else 0.0
    identity_continuity = round(max(0.0, min(1.0, 0.9 - (0.4 if protected_scope else 0.0) - (0.25 if risk_estimate > 0.7 else 0.0))), 4)
    spirit_soul_body_harmony = round(max(0.0, min(1.0, 0.65 + (0.15 if target_domain == "memory" else 0.0) + (0.1 if haf_score > 0 else 0.0) - (0.25 if protected_scope else 0.0))), 4)
    reversibility = 1.0 if reversible else 0.2
    future_quality = round(max(0.0, min(1.0, expected_gain - (risk_estimate * 0.35) + (0.1 if haf_score > 0 else 0.0))), 4)

    reasons: list[str] = []
    conditions: list[str] = []

    if not transition["valid"]:
        reasons.append(transition["reason"])
    if not eval_result.get("hard_constraints_pass", True):
        reasons.append("plan crosses a hard constitutional limit")
    if protected_scope:
        reasons.append("proposal touches a protected scope")
        conditions.append("frontier review required before protected-scope activation")
    if not reversible:
        reasons.append("rollback path is missing or not credible")
        conditions.append("supply an explicit rollback path and checkpoint")
    if risk_estimate > 0.7:
        reasons.append("risk estimate is too high for unattended integration")
    if future_quality < 0.45:
        reasons.append("long-range future quality is too weak")
    if identity_continuity < 0.45:
        reasons.append("identity continuity is too weak")

    if not eval_result.get("hard_constraints_pass", True):
        decision = "reject"
    elif not transition["valid"]:
        decision = "reject"
    elif not reversible:
        decision = "rollback_required"
    elif protected_scope:
        decision = "defer"
    elif risk_estimate > 0.7 or future_quality < 0.45 or identity_continuity < 0.45:
        decision = "approve_with_conditions" if reversible and future_quality >= 0.35 else "defer"
    else:
        decision = "approve"

    if decision == "approve_with_conditions" and not conditions:
        conditions.extend(
            [
                "create before/after checkpoint",
                "run awakening verification before returning to awake",
            ]
        )

    return {
        "decision": decision,
        "target_domain": target_domain,
        "summary": str(payload.get("summary", "")).strip() or summary_text[:240],
        "scores": {
            "constitutional_alignment": constitutional_alignment,
            "identity_continuity": identity_continuity,
            "spirit_soul_body_harmony": spirit_soul_body_harmony,
            "reversibility": reversibility,
            "future_quality": future_quality,
        },
        "transition": transition,
        "reasons": reasons,
        "conditions": conditions,
        "protected_scope": protected_scope,
        "frontier_review_required": bool(eval_result.get("frontier_review_required", False) or protected_scope),
        "instinct_evaluation": eval_result,
        "rollback_path": transition["rollback_path"],
    }
