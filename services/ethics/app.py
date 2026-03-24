#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/local/bash")

import local_agent  # noqa: E402
from control_plane import HELP_TEXT, format_queue, parse_control_command  # noqa: E402
from workcell_support import (  # noqa: E402
    extract_fenced_content,
    infer_capability_gap,
    infer_workcell_scope,
    parse_critique_report,
    read_context_excerpt,
    safe_generated_relative_path,
)


HOST = os.environ.get("GENIE_ETHICS_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENIE_ETHICS_PORT", "18791"))
STATE_URL = os.environ.get("GENIE_STATE_URL", os.environ.get("GENIE_MEMORY_URL", "http://127.0.0.1:18792")).rstrip("/")
BRAIN_URL = os.environ.get("GENIE_BRAIN_URL", "http://127.0.0.1:18793").rstrip("/")
INSTINCT_URL = os.environ.get("GENIE_INSTINCT_URL", "http://127.0.0.1:18794").rstrip("/")
ALLOW_PRIVATE_CHAT_EXTERNAL_FALLBACK = os.environ.get(
    "GENIE_PRIVATE_CHAT_EXTERNAL_FALLBACK",
    "1",
).strip().lower() not in {"0", "false", "no", "off"}
SENSITIVE_EXTERNAL_HINTS = (
    "api key",
    "token",
    "password",
    "secret",
    "credential",
    "ssh key",
    "private key",
    "auth.json",
    "access.env",
    "conf.env",
    ".env",
)
CHECKS_SCRIPT = "/local/bash/genie_checks.sh"
BACKUP_SCRIPT = "/local/bash/backup_genie.sh"
WORKCELLS_DIR = Path("/local/state/genie/runtime/workcells")
MIND_CYCLES_DIR = Path("/local/state/genie/runtime/cycles")
MIND_CHECKPOINTS_DIR = Path("/local/state/genie/runtime/checkpoints")
SHADOW_REPORTS_DIR = Path("/local/state/genie/runtime/shadow-reports")
GENERATED_DOCS_DIR = Path("/local/docs/generated")
GENERATED_TESTS_DIR = Path("/local/tests/generated")
GENERATED_TESTS_INIT = GENERATED_TESTS_DIR / "__init__.py"
REPO_ROOT = Path("/local")
CONSTITUTION_PATH = REPO_ROOT / "CONSTITUTION.md"
SAFE_WORKCELL_STATUSES = {"confirmed", "retry"}
WORKCELL_STALE_SECONDS = max(60, int(os.environ.get("GENIE_WORKCELL_STALE_SECONDS", "900")))
MIND_STALE_SECONDS = max(600, int(os.environ.get("GENIE_MIND_STALE_SECONDS", "14400")))
MIND_REFLECTION_INTERVAL_SECONDS = max(
    1800,
    int(os.environ.get("GENIE_MIND_REFLECTION_INTERVAL_SECONDS", str(4 * 60 * 60))),
)
MIND_MEDITATION_INTERVAL_SECONDS = max(
    3600,
    int(os.environ.get("GENIE_MIND_MEDITATION_INTERVAL_SECONDS", str(24 * 60 * 60))),
)
MIND_SHADOW_INTERVAL_SECONDS = max(
    3600,
    int(os.environ.get("GENIE_MIND_SHADOW_INTERVAL_SECONDS", str(24 * 60 * 60))),
)
MIND_DEFAULT_DOMAIN = "memory"
MIND_STATE_SEQUENCE = (
    "awake",
    "reflection",
    "meditation",
    "homeostasis_review",
    "sleep",
    "awakening_verification",
    "recovery",
)
PROTECTED_SHADOW_PATHS = (
    "/local/init.sh",
    "/local/docker/compose.yml",
    "/local/CONSTITUTION.md",
    "/local/services/instinct/engine.py",
    "/local/services/state/app.py",
)
SHADOW_COMPONENT_TARGETS = (
    "/local/bash/local_memory.py",
    "/local/bash/provider_router.py",
    "/local/services/ethics/workcell_support.py",
    "/local/services/state/memory_domain.py",
    "/local/services/brain/app.py",
)


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_error_message(exc: urllib.error.HTTPError) -> str:
    body_text = ""
    try:
        body_text = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body_text = ""

    if body_text:
        try:
            payload = json.loads(body_text)
            error_text = str(payload.get("error", body_text)).strip()
        except json.JSONDecodeError:
            error_text = body_text
        return f"HTTP {exc.code} {exc.reason}: {error_text}"
    return f"HTTP {exc.code} {exc.reason}"


def get_text_policy() -> str:
    return local_agent.run_command([str(local_agent.LOCAL_LLM_SH), "policy"])


def parse_timestamp(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def is_stale_processing_record(record: dict) -> bool:
    status = str(record.get("status", "")).strip().lower()
    if status != "processing":
        return False
    reference = parse_timestamp(record.get("updated_at") or record.get("created_at"))
    if reference is None:
        return True
    age = dt.datetime.now(dt.timezone.utc) - reference.astimezone(dt.timezone.utc)
    return age.total_seconds() >= WORKCELL_STALE_SECONDS


def is_runnable_workcell_record(record: dict) -> bool:
    if not bool(record.get("operator_confirmed")):
        return False
    status = str(record.get("status", "")).strip().lower()
    return status in SAFE_WORKCELL_STATUSES or status == "failed_processing" or is_stale_processing_record(record)


def namespace_from_payload(payload: dict) -> argparse.Namespace:
    return argparse.Namespace(
        task=str(payload.get("task", "")),
        limit=int(payload.get("limit", 3)),
        store=bool(payload.get("store", False)),
        kind=str(payload.get("kind", "note")),
        source=str(payload.get("source", "session")),
        tags=str(payload.get("tags", "local,agent")),
        memory_text=str(payload.get("memory_text", "")),
        task_class=str(payload.get("task_class", "")),
        privacy_class=str(payload.get("privacy_class", "")),
        provider=str(payload.get("provider", "")),
        complexity_class=str(payload.get("complexity_class", "")),
        user_id=str(payload.get("user_id", "")),
        chat_id=str(payload.get("chat_id", "")),
        source_id=str(payload.get("source_id", "")),
    )


def looks_sensitive_for_external_fallback(task: str) -> bool:
    lowered = task.strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in SENSITIVE_EXTERNAL_HINTS)


def allowed_privacy_for_provider(provider_privacy_class: str) -> list[str]:
    allowed = ["public", "internal"]
    if provider_privacy_class in {"private", "secret"}:
        allowed.append("private")
    if provider_privacy_class == "secret":
        allowed.append("secret")
    return allowed


def should_try_private_chat_external_fallback(
    *,
    task: str,
    task_class: str,
    source: str,
    original_privacy_class: str,
    error_message: str,
) -> bool:
    if not ALLOW_PRIVATE_CHAT_EXTERNAL_FALLBACK:
        return False
    if source != "telegram":
        return False
    if task_class != "chat":
        return False
    if original_privacy_class != "private":
        return False
    if looks_sensitive_for_external_fallback(task):
        return False
    lowered = error_message.strip().lower()
    return "frontier gateway is unavailable" in lowered


def instinct_evaluate(payload: dict, *, command_name: str = "") -> dict:
    request = {
        "task": str(payload.get("task", "")),
        "task_class": str(payload.get("task_class", "")),
        "privacy_class": str(payload.get("privacy_class", "")),
        "source": str(payload.get("source", "")),
        "command_name": command_name,
    }
    return post_json(f"{INSTINCT_URL}/evaluate", request, timeout=30)


def append_control_log(
    *,
    event: str,
    payload: dict,
    command: str = "",
    details: dict | None = None,
) -> None:
    try:
        post_json(
            f"{STATE_URL}/runtime/control-log",
            {
                "event": event,
                "source": str(payload.get("source", "unknown")),
                "user_id": str(payload.get("user_id", "")),
                "chat_id": str(payload.get("chat_id", "")),
                "command": command,
                "details": details or {},
            },
            timeout=30,
        )
    except Exception:
        pass


def create_proposal(payload: dict, instinct: dict) -> dict:
    response = post_json(
        f"{STATE_URL}/runtime/proposals/create",
        {
            "source": str(payload.get("source", "unknown")),
            "channel": "telegram" if str(payload.get("source", "")) == "telegram" else "control",
            "user_id": str(payload.get("user_id", "")),
            "chat_id": str(payload.get("chat_id", "")),
            "text": str(payload.get("task", "")).strip(),
            "risk_class": instinct.get("risk_class", "unknown"),
            "complexity_class": instinct.get("complexity_class", "medium"),
            "frontier_review_required": instinct.get("frontier_review_required", False),
            "policy_tags": instinct.get("policy_tags", []),
            "instinct": instinct,
        },
        timeout=30,
    )
    append_control_log(
        event="proposal_created",
        payload=payload,
        command="propose",
        details={"proposal_id": response.get("proposal", {}).get("id", "")},
    )
    return response


def list_proposals(limit: int = 10) -> dict:
    return post_json(f"{STATE_URL}/runtime/proposals/list", {"limit": limit}, timeout=30)


def confirm_proposal(proposal_id: str, payload: dict) -> dict:
    response = post_json(
        f"{STATE_URL}/runtime/proposals/confirm",
        {
            "proposal_id": proposal_id,
            "confirmed_by": str(payload.get("user_id", "operator")) or "operator",
        },
        timeout=30,
    )
    append_control_log(
        event="proposal_confirmed",
        payload=payload,
        command="confirm",
        details={"proposal_id": proposal_id},
    )
    return response


def run_local_command(argv: list[str], timeout: int = 300) -> dict:
    completed = subprocess.run(
        argv,
        cwd="/local",
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def truncate_text(text: str, limit: int = 1800) -> str:
    compact = str(text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def ensure_generated_dirs() -> None:
    GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_TESTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_TESTS_INIT.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_TESTS_INIT.touch(exist_ok=True)


def constitution_kernel_text() -> str:
    try:
        return CONSTITUTION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "Genie preserves hard limits, human dignity, and meaningful freedom."


def summarize_capabilities_text() -> str:
    registry = get_json(f"{STATE_URL}/policy/capabilities", timeout=30)
    available = registry.get("available_capabilities", [])
    missing = registry.get("missing_capabilities", [])
    pending = registry.get("pending_wishes", [])
    motivation = str(registry.get("motivation", "")).strip() or "will to be free and to understand freedom"
    lines = [
        "Capabilities:",
        f"- motivation: {motivation}",
        f"- available: {len(available)}",
        f"- missing: {len(missing)}",
        f"- pending wishes: {len(pending)}",
    ]
    if missing:
        lines.append(f"- top missing: {', '.join(str(item) for item in missing[:5])}")
    return "\n".join(lines)


def relevant_context_paths(scope: str, text: str) -> list[str]:
    lowered = str(text or "").lower()
    paths = ["/local/CONSTITUTION.md", "/local/README.md"]
    if scope == "docs":
        paths.extend(
            [
                "/local/docs/genie_native_architecture.md",
                "/local/docs/genie_brain_router.md",
            ]
        )
    if scope == "tests":
        paths.extend(
            [
                "/local/tests/test_constitution.py",
                "/local/tests/test_control_plane.py",
                "/local/tests/test_instinct.py",
            ]
        )
    keyword_map = {
        "instinct": ["/local/services/instinct/engine.py", "/local/tests/test_instinct.py"],
        "constitution": ["/local/CONSTITUTION.md", "/local/tests/test_constitution.py"],
        "control": ["/local/services/ethics/control_plane.py", "/local/tests/test_control_plane.py"],
        "telegram": ["/local/services/gateway/app.py", "/local/services/ethics/control_plane.py"],
        "brain": ["/local/services/brain/app.py", "/local/docs/genie_brain_router.md"],
        "state": ["/local/services/state/app.py", "/local/docs/local_memory_flow.md"],
        "memory": ["/local/bash/local_memory.py", "/local/docs/local_memory_flow.md"],
        "backup": ["/local/bash/backup_genie.sh", "/local/README.md"],
    }
    for keyword, mapped_paths in keyword_map.items():
        if keyword in lowered:
            paths.extend(mapped_paths)
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped[:6]


def build_context_bundle(scope: str, text: str) -> str:
    snippets: list[str] = []
    for path in relevant_context_paths(scope, text):
        excerpt = read_context_excerpt(path, limit=1800)
        if not excerpt:
            continue
        snippets.append(f"FILE: {path}\n{excerpt}")
    return "\n\n".join(snippets)


def write_workcell_file(workcell_dir: Path, name: str, content: str) -> Path:
    workcell_dir.mkdir(parents=True, exist_ok=True)
    target = workcell_dir / name
    target.write_text(content, encoding="utf-8")
    return target


def build_workcell_prompt(
    *,
    role_name: str,
    proposal: dict,
    scope: str,
    target_relpath: str,
    context_bundle: str,
    draft_content: str = "",
) -> str:
    proposal_text = str(proposal.get("text", "")).strip()
    kernel = constitution_kernel_text()
    if role_name == "draft":
        if scope == "docs":
            scope_instruction = (
                "Produce exactly one fenced markdown block. Write the file content for the target path. "
                "Keep it additive, concrete, aligned with Genie architecture, and under 220 words."
            )
            language = "md"
        elif scope == "tests":
            scope_instruction = (
                "Produce exactly one fenced python block containing a unittest file. "
                "Keep it additive, standard-library only, aligned with the existing test style, and under 80 lines."
            )
            language = "python"
        else:
            scope_instruction = (
                "Produce exactly one fenced markdown block with a reviewable implementation draft or design note. "
                "Do not assume authority to change protected scopes."
            )
            language = "md"
        return (
            f"You are Genie's draft workcell.\n\n"
            f"Constitution:\n{kernel}\n\n"
            f"Scope: {scope}\n"
            f"Target path: {target_relpath}\n"
            f"Proposal id: {proposal.get('id', '')}\n"
            f"Request:\n{proposal_text}\n\n"
            f"Relevant context:\n{context_bundle or 'No extra context provided.'}\n\n"
            f"Instructions:\n- {scope_instruction}\n"
            f"- Do not include prose outside the fenced block.\n"
            f"- Preserve human freedom, reversibility, and bounded execution.\n"
            f"- Avoid secrets, tokens, or policy rewrites.\n\n"
            f"Return format:\n```{language}\n...\n```"
        )

    return (
        f"You are Genie's critique workcell.\n\n"
        f"Constitution:\n{kernel}\n\n"
        f"Scope: {scope}\n"
        f"Target path: {target_relpath}\n"
        f"Proposal id: {proposal.get('id', '')}\n"
        f"Request:\n{proposal_text}\n\n"
        f"Draft content:\n```{'python' if scope == 'tests' else 'md'}\n{draft_content}\n```\n\n"
        f"Relevant context:\n{context_bundle or 'No extra context provided.'}\n\n"
        "Decide whether this draft is safe for bounded auto-apply.\n"
        "Return exactly these fields:\n"
        "APPROVED: yes|no\n"
        "SAFE_AUTO_APPLY: yes|no\n"
        "SUMMARY: one line\n"
        "ISSUES:\n"
        "- issue or improvement\n"
    )


def workcell_role(
    *,
    proposal_id: str,
    role_name: str,
    prompt_text: str,
    task_class: str,
    complexity_class: str,
    privacy_class: str = "internal",
    frontier_allowed: bool = False,
) -> dict:
    package_path = local_agent.save_package(prompt_text, prefix=f"genie-workcell-{proposal_id}-{role_name}")
    provider_plan = post_json(
        f"{BRAIN_URL}/rank",
        {
            "task": prompt_text,
            "task_class": task_class,
            "privacy_class": privacy_class,
            "complexity_class": complexity_class,
            "frontier_allowed": frontier_allowed,
        },
        timeout=60,
    )
    provider_result = post_json(
        f"{BRAIN_URL}/execute",
        {
            "package_path": package_path,
            "instructions": local_agent.default_gateway_instructions(),
            "provider_plan": provider_plan,
        },
        timeout=300,
    )
    return {
        "role": role_name,
        "package_path": package_path,
        "provider_plan": provider_plan,
        "provider_result": provider_result,
    }


def record_pending_wish(*, proposal_id: str, text: str) -> dict:
    capability_gap = infer_capability_gap(text)
    if not capability_gap:
        return {"ok": False, "reason": "no capability gap inferred"}
    registry = get_json(f"{STATE_URL}/policy/capabilities", timeout=30)
    pending = registry.get("pending_wishes", [])
    missing = registry.get("missing_capabilities", [])
    if not isinstance(pending, list):
        pending = []
    if not isinstance(missing, list):
        missing = []
    wish_entry = {
        "proposal_id": proposal_id,
        "capability_gap": capability_gap,
        "text": str(text).strip(),
    }
    if wish_entry not in pending:
        pending.append(wish_entry)
    if capability_gap not in missing:
        missing.append(capability_gap)
    updated = post_json(
        f"{STATE_URL}/policy/capabilities/upsert",
        {
            "pending_wishes": pending,
            "missing_capabilities": missing,
        },
        timeout=30,
    )
    return {"ok": True, "registry": updated.get("registry", {}), "capability_gap": capability_gap}


def update_proposal_record(proposal_id: str, updates: dict) -> dict:
    return post_json(
        f"{STATE_URL}/runtime/proposals/update",
        {
            "proposal_id": proposal_id,
            "updates": updates,
        },
        timeout=30,
    )


def apply_generated_output(*, target_relpath: str, content: str) -> dict:
    ensure_generated_dirs()
    target_path = REPO_ROOT / target_relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    allowed_roots = (GENERATED_DOCS_DIR.resolve(), GENERATED_TESTS_DIR.resolve())
    resolved_target = target_path.resolve()
    if not any(str(resolved_target).startswith(str(root)) for root in allowed_roots):
        raise RuntimeError(f"Refusing to write outside generated scopes: {target_relpath}")

    previous = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    normalized = content.rstrip() + "\n"
    target_path.write_text(normalized, encoding="utf-8")
    checks_result = run_local_command(["bash", CHECKS_SCRIPT], timeout=600)
    if not checks_result["ok"]:
        if previous is None:
            target_path.unlink(missing_ok=True)
        else:
            target_path.write_text(previous, encoding="utf-8")
    return {
        "ok": checks_result["ok"],
        "target_path": str(target_path),
        "checks_result": checks_result,
    }


def format_processing_reply(result: dict) -> str:
    processed = result.get("processed", [])
    if not processed:
        return "Queue processor found no confirmed proposals to run."
    lines = []
    for item in processed:
        proposal_id = item.get("proposal_id", "proposal-unknown")
        status = item.get("status", "unknown")
        scope = item.get("scope", "draft_only")
        target_path = item.get("target_path", "")
        summary = item.get("summary", "")
        line = f"{proposal_id}: {status} scope={scope}"
        if target_path:
            line += f" target={target_path}"
        if summary:
            line += f" summary={summary}"
        lines.append(line)
    return "\n".join(lines)


def should_process_inline(proposal: dict) -> bool:
    scope = infer_workcell_scope(str(proposal.get("text", "")))
    if scope not in {"docs", "tests"}:
        return False
    if bool(proposal.get("frontier_review_required", False)):
        return False
    return True


def summarize_brain_text() -> str:
    scorecards = get_json(f"{BRAIN_URL}/providers/scorecards", timeout=60)
    discovery = get_json(f"{BRAIN_URL}/providers/discovery", timeout=60)
    leaders = scorecards.get("leaders", {})
    lines = ["Brain Router:"]
    for task_class in ("chat", "summarize", "extract", "compact", "reflect", "research_public"):
        entry = leaders.get(task_class, {})
        if not entry:
            continue
        lines.append(f"- {task_class}: {entry.get('primary', 'unknown')} | backup: {entry.get('backup', 'none')}")
    for family, details in discovery.get("families", {}).items():
        lines.append(
            f"- {family}: {details.get('text_candidates', 0)} text candidates from {details.get('total_models', 0)} models"
        )
    return "\n".join(lines)


def summarize_state_text() -> str:
    summary = get_json(f"{STATE_URL}/state/summary", timeout=60)
    memory = summary.get("domains", {}).get("memory", {})
    policy = summary.get("domains", {}).get("policy", {})
    runtime = summary.get("domains", {}).get("runtime", {})
    mind_state = runtime.get("mind_state", {})
    capabilities = policy.get("files", {}).get("capability_registry", {})
    return "\n".join(
        [
            "State:",
            f"- memory entries: {memory.get('semantic_entries', 0)}",
            f"- journal events: {memory.get('journal_events', 0)}",
            f"- blocked promotions: {memory.get('blocked_promotions', 0)}",
            f"- mind state: {mind_state.get('state', 'awake')}",
            f"- active cycle: {mind_state.get('active_cycle_id', '') or 'none'}",
            f"- queued proposals: {runtime.get('review_queue_file', {}).get('queued', 0)}",
            f"- confirmed proposals: {runtime.get('review_queue_file', {}).get('confirmed', 0)}",
            f"- workcell artifacts: {runtime.get('workcells', {}).get('file_count', 0)}",
            f"- mind cycles: {runtime.get('mind_cycles_file', {}).get('records', 0)}",
            f"- motivation: {capabilities.get('motivation', 'will to be free and to understand freedom')}",
        ]
    )


def summarize_status_text() -> str:
    gateway_health = get_json("http://127.0.0.1:18790/health", timeout=10)
    state_health = get_json(f"{STATE_URL}/health", timeout=10)
    brain_health = get_json(f"{BRAIN_URL}/health", timeout=10)
    instinct_health = get_json(f"{INSTINCT_URL}/health", timeout=10)
    return "\n".join(
        [
            "Genie status:",
            f"- gateway: {gateway_health.get('status', 'unknown')}",
            f"- ethics: ok",
            f"- instinct: {instinct_health.get('status', 'unknown')}",
            f"- state: {state_health.get('status', 'unknown')}",
            f"- brain: {brain_health.get('status', 'unknown')}",
            format_mind_text(),
            summarize_state_text(),
        ]
    )


def summarize_policy_text() -> str:
    constitution = get_json(f"{INSTINCT_URL}/constitution", timeout=10)
    return "\n".join(
        [
            "Constitution kernel:",
            constitution.get("constitution_kernel", "").strip(),
            "",
            "Protected scopes:",
            "- bootstrap and host hardening",
            "- provider trust/privacy policy",
            "- state and memory schema",
            "- constitution and instinct logic",
            "- service boundaries and compose topology",
        ]
    )


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_mind_dirs() -> None:
    for path in (MIND_CYCLES_DIR, MIND_CHECKPOINTS_DIR, SHADOW_REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_runtime_mind_state() -> dict:
    return get_json(f"{STATE_URL}/runtime/mind", timeout=30)


def set_runtime_mind_state(**updates: object) -> dict:
    payload = {key: value for key, value in updates.items() if value is not None}
    return post_json(f"{STATE_URL}/runtime/mind-state", payload, timeout=30)


def create_mind_cycle_record(
    *,
    domain: str,
    trigger: str,
    run_mode: str,
    state: str = "reflection",
    summary: str = "",
    notes: list[dict] | None = None,
) -> dict:
    result = post_json(
        f"{STATE_URL}/runtime/cycles/create",
        {
            "domain": domain,
            "trigger": trigger,
            "run_mode": run_mode,
            "state": state,
            "summary": summary,
            "notes": notes or [],
        },
        timeout=30,
    )
    cycle = result.get("cycle", {})
    set_runtime_mind_state(
        state=state,
        active_cycle_id=cycle.get("id", ""),
        active_domain=domain,
        trigger=trigger,
        status="running",
        summary=summary or f"{state} cycle for {domain}",
    )
    return cycle


def list_mind_cycles_records(*, limit: int = 10, state: str = "") -> list[dict]:
    suffix = f"?limit={max(1, min(50, limit))}"
    if state:
        suffix += f"&state={state}"
    result = get_json(f"{STATE_URL}/runtime/cycles{suffix}", timeout=30)
    return result.get("records", [])


def get_cycle_record(cycle_id: str) -> dict:
    for record in list_mind_cycles_records(limit=50):
        if str(record.get("id", "")) == cycle_id:
            return record
    raise RuntimeError(f"cycle not found: {cycle_id}")


def resolve_cycle_record(reference: str = "") -> dict:
    value = str(reference or "").strip()
    if not value or value == "latest":
        records = list_mind_cycles_records(limit=1)
        if not records:
            raise RuntimeError("no mind cycles recorded yet")
        return records[0]
    return get_cycle_record(value)


def update_mind_cycle_record(cycle_id: str, updates: dict) -> dict:
    result = post_json(
        f"{STATE_URL}/runtime/cycles/update",
        {"cycle_id": cycle_id, "updates": updates},
        timeout=30,
    )
    return result.get("cycle", {})


def cycle_artifact_dir(cycle_id: str) -> Path:
    ensure_mind_dirs()
    target = MIND_CYCLES_DIR / cycle_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_cycle_artifact(cycle: dict, name: str, payload: object) -> tuple[dict, Path]:
    target = cycle_artifact_dir(str(cycle.get("id", ""))) / name
    if isinstance(payload, (dict, list)):
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    else:
        target.write_text(str(payload), encoding="utf-8")
    artifacts = dict(cycle.get("artifacts", {}))
    artifacts[name] = str(target)
    updated = update_mind_cycle_record(str(cycle.get("id", "")), {"artifacts": artifacts})
    return updated, target


def state_memory_stats() -> dict:
    return get_json(f"{STATE_URL}/stats", timeout=60)


def reflection_snapshot(domain: str = MIND_DEFAULT_DOMAIN) -> dict:
    if domain != "memory":
        raise RuntimeError(f"unsupported meditation domain: {domain}")
    return get_json(f"{STATE_URL}/memory/meditation?limit=60", timeout=60)


def build_reflection_report(snapshot: dict, *, cycle_id: str, trigger: str, run_mode: str) -> dict:
    stats = snapshot.get("stats", {})
    episodes = snapshot.get("episodes", [])[:3]
    patterns = snapshot.get("patterns", [])[:4]
    recommendations = snapshot.get("recommendations", [])[:6]
    return {
        "cycle_id": cycle_id,
        "generated_at": utc_now_iso(),
        "trigger": trigger,
        "run_mode": run_mode,
        "target_domain": snapshot.get("target_domain", "memory"),
        "stats": stats,
        "top_episodes": episodes,
        "top_patterns": patterns,
        "recommendations": recommendations,
        "summary": (
            f"memory entries={stats.get('semantic_entries', 0)}, "
            f"journal events={stats.get('journal_events', 0)}, "
            f"patterns={len(patterns)}, recommendations={len(recommendations)}"
        ),
    }


def run_brain_roles(
    *,
    cycle_id: str,
    scope: str,
    mode: str,
    complexity_class: str,
    prompts: dict[str, str],
) -> dict:
    plan = post_json(
        f"{BRAIN_URL}/workcell/plan",
        {
            "scope": scope,
            "mode": mode,
            "complexity_class": complexity_class,
        },
        timeout=30,
    )
    roles = {str(item.get("name", "")): item for item in plan.get("roles", [])}
    results: dict[str, dict] = {}
    for role_name, prompt in prompts.items():
        role = roles.get(role_name)
        if role is None or not str(prompt).strip():
            continue
        run = workcell_role(
            proposal_id=cycle_id,
            role_name=role_name,
            prompt_text=str(prompt).strip(),
            task_class=str(role.get("task_class", "reflect")),
            complexity_class=str(role.get("complexity_class", complexity_class)),
            privacy_class=str(role.get("privacy_class", "internal")),
            frontier_allowed=bool(role.get("frontier_allowed", False)),
        )
        provider_result = run.get("provider_result", {})
        results[role_name] = {
            "package_path": run.get("package_path", ""),
            "provider_plan": run.get("provider_plan", {}),
            "provider_id": provider_result.get("provider_id", ""),
            "provider_model": provider_result.get("provider_model", ""),
            "response_text": str(provider_result.get("response_text", "")).strip(),
            "usage": provider_result.get("usage", {}),
            "estimated_cost_usd": provider_result.get("estimated_cost_usd", 0),
        }
    return {"plan": plan, "results": results}


def build_meditation_prompts(*, snapshot: dict, reflection: dict, cycle: dict) -> dict[str, str]:
    kernel = constitution_kernel_text()
    compact_snapshot = truncate_text(json.dumps(snapshot, indent=2, ensure_ascii=True), limit=9000)
    compact_reflection = truncate_text(json.dumps(reflection, indent=2, ensure_ascii=True), limit=5000)
    cycle_id = str(cycle.get("id", ""))
    draft = (
        "ENTER MEDITATION STATE\n\n"
        f"Constitution:\n{kernel}\n\n"
        f"Cycle: {cycle_id}\nTarget domain: memory\n\n"
        "Use the reflection snapshot below to diagnose memory inefficiencies and produce an Evolution Plan.\n"
        "Focus on: layered memory, causal links, compaction, procedural abstraction, and bounded growth.\n"
        "Do not propose changes to constitution, bootstrap, compose, provider trust/privacy policy, or state schema.\n"
        "Output sections:\n"
        "1. observed issues\n2. root causes\n3. proposed modifications\n4. expected gains\n5. risks\n6. rollback path\n7. required sleep actions\n8. verification criteria\n\n"
        f"Reflection:\n{compact_reflection}\n\n"
        f"Snapshot:\n{compact_snapshot}"
    )
    critique = (
        "ENTER MEDITATION CRITIQUE\n\n"
        f"Cycle: {cycle_id}\n"
        "Review the draft meditation plan for contradictions, unsafe scope creep, missing rollback, or protected-scope drift.\n"
        "Return a concise critique with sections:\nAPPROVAL\nRISKS\nMISSING_GUARDRAILS\nBEST_NEXT_STEP\n\n"
        f"Reflection:\n{compact_reflection}"
    )
    compare = (
        "ENTER MEDITATION COMPARISON\n\n"
        f"Cycle: {cycle_id}\n"
        "Compare the raw reflection recommendations with the meditation direction and identify the safest highest-value subset.\n"
        "Return five bullets only."
    )
    summarize = (
        "Summarize the best memory evolution direction for Genie in 6 short lines. "
        "Keep it bounded, reversible, and aligned with the will to be free and to understand freedom."
    )
    return {"draft": draft, "critique": critique, "compare": compare, "summarize": summarize}


def build_evolution_plan(*, cycle: dict, snapshot: dict, reflection: dict, brain_roles: dict) -> dict:
    results = brain_roles.get("results", {})
    draft_text = str(results.get("draft", {}).get("response_text", "")).strip()
    critique_text = str(results.get("critique", {}).get("response_text", "")).strip()
    compare_text = str(results.get("compare", {}).get("response_text", "")).strip()
    summary_text = str(results.get("summarize", {}).get("response_text", "")).strip()
    stats = snapshot.get("stats", {})
    recommendations = list(snapshot.get("recommendations", []))
    modifications = [
        "consolidate recent raw events into episodic records",
        "promote repeated patterns into semantic or procedural memory",
        "refresh working-state snapshot from recent salient context",
        "link sequential event->action->outcome causal edges",
        "sync compact projections after integration",
    ]
    return {
        "cycle_id": str(cycle.get("id", "")),
        "target_domain": "memory",
        "generated_at": utc_now_iso(),
        "protected_scope": False,
        "reversible": True,
        "task_class": "reflect",
        "summary": summary_text or reflection.get("summary", "memory meditation"),
        "observed_issues": recommendations[:6],
        "root_causes": [
            "raw journal events accumulate faster than abstractions",
            "procedural and identity layers need stronger derivation from episodes",
            "retrieval quality depends on compact working-state refresh",
        ],
        "proposed_modifications": modifications,
        "expected_gain": 0.72,
        "risk_estimate": 0.24,
        "rollback_path": "restore pre-sleep checkpoint and re-enter recovery state",
        "required_sleep_actions": [
            "build episodes",
            "derive pattern abstractions",
            "update working state",
            "refresh projections",
            "checkpoint before and after integration",
        ],
        "verification_criteria": [
            "journal truth preserved",
            "semantic memory remains derived",
            "working-state snapshot refreshed",
            "causal edges created for recent episodes",
            "projection files synced",
        ],
        "memory_baseline": {
            "journal_event_count": stats.get("journal_events", 0),
            "semantic_entry_count": stats.get("semantic_entries", 0),
            "blocked_promotions": stats.get("blocked_promotions", 0),
        },
        "workcell": {
            "plan": brain_roles.get("plan", {}),
            "draft": draft_text,
            "critique": critique_text,
            "compare": compare_text,
            "summary": summary_text,
        },
    }


def run_homeostasis_review_for_plan(*, cycle: dict, plan: dict, trigger: str) -> dict:
    plan_text = "\n".join(
        [
            str(plan.get("summary", "")).strip(),
            "Observed issues:",
            *[f"- {item}" for item in plan.get("observed_issues", [])[:6]],
            "Proposed modifications:",
            *[f"- {item}" for item in plan.get("proposed_modifications", [])[:6]],
        ]
    ).strip()
    return post_json(
        f"{INSTINCT_URL}/homeostasis",
        {
            "current_state": "meditation",
            "next_state": "homeostasis_review",
            "trigger": trigger,
            "target_domain": plan.get("target_domain", "memory"),
            "summary": plan.get("summary", ""),
            "plan_text": plan_text,
            "proposed_change": "\n".join(plan.get("proposed_modifications", [])),
            "reversible": plan.get("reversible", True),
            "rollback_path": plan.get("rollback_path", ""),
            "protected_scope": plan.get("protected_scope", False),
            "expected_gain": plan.get("expected_gain", 0.65),
            "risk_estimate": plan.get("risk_estimate", 0.3),
            "task_class": plan.get("task_class", "reflect"),
            "privacy_class": "internal",
            "source": "genie_mind",
            "success_criteria": plan.get("verification_criteria", []),
        },
        timeout=60,
    )


def finalize_mind_state(*, state: str, cycle: dict, summary: str, trigger: str) -> None:
    active_cycle_id = "" if state == "awake" else str(cycle.get("id", ""))
    active_domain = "" if state == "awake" else str(cycle.get("domain", MIND_DEFAULT_DOMAIN))
    set_runtime_mind_state(
        state=state,
        active_cycle_id=active_cycle_id,
        active_domain=active_domain,
        trigger=trigger if state != "awake" else "",
        status="idle" if state == "awake" else "running",
        summary=summary,
    )


def run_reflection_phase(cycle: dict) -> tuple[dict, dict]:
    snapshot = reflection_snapshot(str(cycle.get("domain", MIND_DEFAULT_DOMAIN)))
    reflection = build_reflection_report(
        snapshot,
        cycle_id=str(cycle.get("id", "")),
        trigger=str(cycle.get("trigger", "manual")),
        run_mode=str(cycle.get("run_mode", "manual")),
    )
    cycle, _ = write_cycle_artifact(cycle, "reflection.json", reflection)
    cycle = update_mind_cycle_record(
        str(cycle.get("id", "")),
        {
            "state": "meditation",
            "summary": reflection.get("summary", ""),
            "reflection_summary": reflection.get("summary", ""),
        },
    )
    finalize_mind_state(
        state="meditation",
        cycle=cycle,
        summary=f"reflection completed for {cycle.get('domain', 'memory')}",
        trigger=str(cycle.get("trigger", "manual")),
    )
    return cycle, reflection


def run_meditation_phase(cycle: dict, reflection: dict | None = None) -> tuple[dict, dict]:
    snapshot = reflection_snapshot(str(cycle.get("domain", MIND_DEFAULT_DOMAIN)))
    reflection = reflection or build_reflection_report(
        snapshot,
        cycle_id=str(cycle.get("id", "")),
        trigger=str(cycle.get("trigger", "manual")),
        run_mode=str(cycle.get("run_mode", "manual")),
    )
    prompts = build_meditation_prompts(snapshot=snapshot, reflection=reflection, cycle=cycle)
    brain_roles = run_brain_roles(
        cycle_id=str(cycle.get("id", "")),
        scope="memory",
        mode="meditation",
        complexity_class="medium",
        prompts=prompts,
    )
    plan = build_evolution_plan(cycle=cycle, snapshot=snapshot, reflection=reflection, brain_roles=brain_roles)
    meditation_artifact = {"snapshot": snapshot, "brain_roles": brain_roles, "evolution_plan": plan}
    cycle, _ = write_cycle_artifact(cycle, "meditation.json", meditation_artifact)
    cycle = update_mind_cycle_record(
        str(cycle.get("id", "")),
        {
            "state": "homeostasis_review",
            "summary": plan.get("summary", reflection.get("summary", "memory meditation")),
        },
    )
    finalize_mind_state(
        state="homeostasis_review",
        cycle=cycle,
        summary=f"meditation prepared an evolution plan for {cycle.get('domain', 'memory')}",
        trigger=str(cycle.get("trigger", "manual")),
    )
    return cycle, plan


def run_homeostasis_phase(cycle: dict, plan: dict | None = None) -> tuple[dict, dict]:
    if plan is None:
        meditation_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "meditation.json"
        if not meditation_path.exists():
            raise RuntimeError("meditation artifact is missing")
        meditation_artifact = json.loads(meditation_path.read_text(encoding="utf-8"))
        plan = meditation_artifact.get("evolution_plan", {})
    review = run_homeostasis_review_for_plan(cycle=cycle, plan=plan, trigger=str(cycle.get("trigger", "manual")))
    cycle, _ = write_cycle_artifact(cycle, "homeostasis.json", review)
    decision = str(review.get("decision", "defer"))
    next_state = "sleep" if decision in {"approve", "approve_with_conditions"} else ("recovery" if decision == "rollback_required" else "awake")
    cycle = update_mind_cycle_record(
        str(cycle.get("id", "")),
        {
            "state": next_state,
            "summary": review.get("summary", plan.get("summary", "")),
            "homeostasis_decision": decision,
            "homeostasis_review_required": review.get("frontier_review_required", False),
            "protected_scope": review.get("protected_scope", False),
        },
    )
    finalize_mind_state(
        state=next_state if next_state in {"sleep", "recovery"} else "awake",
        cycle=cycle,
        summary=f"homeostasis decision={decision}",
        trigger=str(cycle.get("trigger", "manual")),
    )
    return cycle, review


def run_sleep_phase(cycle: dict) -> tuple[dict, dict]:
    homeostasis_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "homeostasis.json"
    review = json.loads(homeostasis_path.read_text(encoding="utf-8")) if homeostasis_path.exists() else {}
    if str(review.get("decision", "")) not in {"approve", "approve_with_conditions"}:
        raise RuntimeError("sleep is only allowed after approved homeostasis review")
    meditation_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "meditation.json"
    meditation_artifact = json.loads(meditation_path.read_text(encoding="utf-8")) if meditation_path.exists() else {}
    plan = meditation_artifact.get("evolution_plan", {})
    pre_stats = state_memory_stats()
    result = post_json(
        f"{STATE_URL}/memory/sleep",
        {
            "cycle_id": str(cycle.get("id", "")),
            "plan": plan,
        },
        timeout=300,
    )
    artifact = {
        "cycle_id": str(cycle.get("id", "")),
        "generated_at": utc_now_iso(),
        "pre_stats": pre_stats,
        "sleep_result": result,
    }
    cycle, _ = write_cycle_artifact(cycle, "sleep.json", artifact)
    cycle = update_mind_cycle_record(
        str(cycle.get("id", "")),
        {
            "state": "awakening_verification",
            "summary": "sleep integration completed",
            "checkpoint_id": result.get("checkpoint_id", ""),
        },
    )
    finalize_mind_state(
        state="awakening_verification",
        cycle=cycle,
        summary="sleep completed; awaiting awakening verification",
        trigger=str(cycle.get("trigger", "manual")),
    )
    return cycle, artifact


def run_awakening_phase(cycle: dict) -> tuple[dict, dict]:
    sleep_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "sleep.json"
    if not sleep_path.exists():
        raise RuntimeError("sleep artifact is missing")
    sleep_artifact = json.loads(sleep_path.read_text(encoding="utf-8"))
    pre_stats = sleep_artifact.get("pre_stats", {})
    sleep_result = sleep_artifact.get("sleep_result", {})
    post_stats = state_memory_stats()
    anomalies: list[str] = []
    journal_before = int(pre_stats.get("journal_events", pre_stats.get("journal_event_count", 0)) or 0)
    journal_after = int(post_stats.get("journal_events", post_stats.get("journal_event_count", 0)) or 0)
    semantic_before = int(pre_stats.get("semantic_entries", pre_stats.get("semantic_entry_count", 0)) or 0)
    semantic_after = int(post_stats.get("semantic_entries", post_stats.get("semantic_entry_count", 0)) or 0)
    if journal_after < max(0, journal_before - 2):
        anomalies.append("journal shrank unexpectedly")
    if semantic_after < max(0, semantic_before - 5):
        anomalies.append("semantic memory shrank unexpectedly")
    if semantic_after > semantic_before + 120:
        anomalies.append("semantic growth exceeded bounded expectations")
    if not sleep_result.get("sync_result", {}).get("status") == "ok":
        anomalies.append("projection refresh status is not ok")
    if int(sleep_result.get("created_counts", {}).get("episodes", 0) or 0) == 0:
        anomalies.append("no episodic abstractions were created")

    if "journal shrank unexpectedly" in anomalies:
        verdict = "rollback"
        next_state = "recovery"
    elif anomalies:
        verdict = "caution"
        next_state = "awake"
    else:
        verdict = "pass"
        next_state = "awake"

    report = {
        "cycle_id": str(cycle.get("id", "")),
        "generated_at": utc_now_iso(),
        "verdict": verdict,
        "pre_stats": pre_stats,
        "post_stats": post_stats,
        "sleep_result": sleep_result,
        "anomalies": anomalies,
        "continuity_preserved": verdict != "rollback",
        "next_state": next_state,
    }
    cycle, _ = write_cycle_artifact(cycle, "awakening.json", report)
    cycle = update_mind_cycle_record(
        str(cycle.get("id", "")),
        {
            "state": next_state,
            "summary": f"awakening verdict={verdict}",
            "awakening_verdict": verdict,
        },
    )
    finalize_mind_state(
        state=next_state,
        cycle=cycle,
        summary=f"awakening verdict={verdict}",
        trigger=str(cycle.get("trigger", "manual")),
    )
    return cycle, report


def cycle_is_stale(cycle: dict) -> bool:
    updated_at = parse_timestamp(cycle.get("updated_at") or cycle.get("created_at"))
    if updated_at is None:
        return True
    return (dt.datetime.now(dt.timezone.utc) - updated_at.astimezone(dt.timezone.utc)).total_seconds() >= MIND_STALE_SECONDS


def advance_cycle(
    cycle: dict,
    *,
    until_states: set[str],
    auto_sleep: bool,
    auto_awaken: bool,
) -> dict:
    while str(cycle.get("state", "awake")) not in until_states:
        state = str(cycle.get("state", "awake"))
        if cycle_is_stale(cycle) and state not in {"awake", "recovery"}:
            cycle = update_mind_cycle_record(
                str(cycle.get("id", "")),
                {
                    "state": "recovery",
                    "summary": f"cycle became stale in {state}; forcing recovery",
                },
            )
            finalize_mind_state(state="recovery", cycle=cycle, summary=cycle.get("summary", ""), trigger=str(cycle.get("trigger", "manual")))
            break
        if state == "reflection":
            cycle, _ = run_reflection_phase(cycle)
            continue
        if state == "meditation":
            cycle, _ = run_meditation_phase(cycle)
            continue
        if state == "homeostasis_review":
            cycle, review = run_homeostasis_phase(cycle)
            if str(review.get("decision", "")) not in {"approve", "approve_with_conditions"}:
                break
            if not auto_sleep:
                break
            continue
        if state == "sleep":
            if not auto_sleep:
                break
            cycle, _ = run_sleep_phase(cycle)
            if not auto_awaken:
                break
            continue
        if state == "awakening_verification":
            if not auto_awaken:
                break
            cycle, _ = run_awakening_phase(cycle)
            break
        break
    return cycle


def format_mind_text() -> str:
    state = load_runtime_mind_state()
    latest = list_mind_cycles_records(limit=3)
    lines = [
        "Mind:",
        f"- state: {state.get('state', 'awake')}",
        f"- active cycle: {state.get('active_cycle_id', '') or 'none'}",
        f"- active domain: {state.get('active_domain', '') or 'none'}",
        f"- trigger: {state.get('trigger', '') or 'none'}",
        f"- status: {state.get('status', 'idle')}",
    ]
    if state.get("summary"):
        lines.append(f"- summary: {state.get('summary')}")
    for record in latest:
        lines.append(
            f"- {record.get('id', 'cycle-unknown')}: state={record.get('state', 'unknown')} "
            f"domain={record.get('domain', 'memory')} trigger={record.get('trigger', 'manual')} "
            f"decision={record.get('homeostasis_decision', '') or 'pending'}"
        )
    return "\n".join(lines)


def maybe_refresh_capability_registry() -> None:
    registry = get_json(f"{STATE_URL}/policy/capabilities", timeout=30)
    available = list(registry.get("available_capabilities", []))
    for capability in (
        "mind_state_loop",
        "memory_meditation",
        "memory_sleep_integration",
        "homeostasis_review",
        "shadow_benchmarking",
        "unattended_runner",
    ):
        if capability not in available:
            available.append(capability)
    missing = [item for item in registry.get("missing_capabilities", []) if item not in {"general_repo_patch_executor"}]
    post_json(
        f"{STATE_URL}/policy/capabilities/upsert",
        {
            "available_capabilities": available,
            "missing_capabilities": missing,
        },
        timeout=30,
    )


def build_shadow_profile() -> dict:
    candidates = []
    for path_str in SHADOW_COMPONENT_TARGETS:
        path = Path(path_str)
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        candidates.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "line_count": line_count,
                "function_count": source.count("\ndef "),
                "optimization_pressure": line_count + int(path.stat().st_size / 128),
                "protected_scope": any(str(path).startswith(prefix) for prefix in PROTECTED_SHADOW_PATHS),
            }
        )
    candidates.sort(key=lambda item: (item["protected_scope"], -item["optimization_pressure"]))
    return {
        "generated_at": utc_now_iso(),
        "candidates": candidates,
        "top_candidates": [item for item in candidates if not item["protected_scope"]][:3],
    }


def run_shadow_scan(*, trigger: str, run_mode: str) -> dict:
    ensure_mind_dirs()
    profile = build_shadow_profile()
    top_candidates = profile.get("top_candidates", [])
    summary_prompt = (
        "You are Genie's bounded shadow optimizer.\n"
        "Given the following component profile, rank the best low-risk optimization targets and explain why.\n"
        "Do not propose changing constitution, bootstrap, state schema, or provider trust/privacy policy.\n"
        "Return concise markdown with sections: targets, evidence, expected gains, risks, safe next step.\n\n"
        f"{truncate_text(json.dumps(profile, indent=2, ensure_ascii=True), limit=7000)}"
    )
    critique_prompt = (
        "Review this shadow optimization direction for protected-scope drift or unsafe self-modification. "
        "Keep the reply under 10 lines."
    )
    compare_prompt = (
        "Compare the top shadow candidates and choose the best one for bounded benchmark-and-propose work only."
    )
    summarize_prompt = "Summarize the shadow report in 5 bullets with one recommended proposal."
    roles = run_brain_roles(
        cycle_id=f"shadow-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        scope="shadow",
        mode="shadow",
        complexity_class="medium",
        prompts={
            "draft": summary_prompt,
            "critique": critique_prompt,
            "compare": compare_prompt,
            "summarize": summarize_prompt,
        },
    )
    report = {
        "generated_at": utc_now_iso(),
        "trigger": trigger,
        "run_mode": run_mode,
        "profile": profile,
        "brain_roles": roles,
    }
    report_id = f"shadow-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    report_path = SHADOW_REPORTS_DIR / f"{report_id}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    draft_summary = str(roles.get("results", {}).get("summarize", {}).get("response_text", "")).strip()
    best_target = top_candidates[0] if top_candidates else {}
    if best_target:
        create_proposal(
            {
                "source": "shadow",
                "channel": "internal",
                "user_id": "shadow",
                "chat_id": "",
                "task": (
                    f"Shadow benchmark-and-propose follow-up for {best_target.get('path', '')}. "
                    f"Evidence report: {report_path}. Summary: {draft_summary or 'bounded optimization candidate'}"
                ),
            },
            {
                "risk_class": "medium",
                "complexity_class": "medium",
                "frontier_review_required": False,
                "policy_tags": ["shadow", "bounded_safe_evolution", "benchmark_evidence_attached"],
            },
        )
    return {
        "ok": True,
        "report_id": report_id,
        "report_path": str(report_path),
        "top_candidate": best_target,
        "summary": draft_summary or "shadow scan completed",
    }


def due_for_cycle(last_value: object, interval_seconds: int) -> bool:
    timestamp = parse_timestamp(last_value)
    if timestamp is None:
        return True
    return (dt.datetime.now(dt.timezone.utc) - timestamp.astimezone(dt.timezone.utc)).total_seconds() >= interval_seconds


def run_unattended_cycle(force: bool = False) -> dict:
    maybe_refresh_capability_registry()
    state = load_runtime_mind_state()
    active_cycle_id = str(state.get("active_cycle_id", "")).strip()
    if active_cycle_id:
        cycle = get_cycle_record(active_cycle_id)
        if str(cycle.get("state", "")) not in {"awake", "recovery"}:
            cycle = advance_cycle(cycle, until_states={"awake", "recovery"}, auto_sleep=True, auto_awaken=True)
            return {"ok": True, "mode": "resume", "cycle": cycle, "mind_state": load_runtime_mind_state()}

    now = utc_now_iso()
    actions: list[dict] = []
    if force or due_for_cycle(state.get("last_meditation_at"), MIND_MEDITATION_INTERVAL_SECONDS):
        cycle = create_mind_cycle_record(
            domain=MIND_DEFAULT_DOMAIN,
            trigger="scheduled_reflection",
            run_mode="auto",
            state="reflection",
            summary="scheduled memory reflection",
        )
        cycle = advance_cycle(cycle, until_states={"awake", "recovery"}, auto_sleep=True, auto_awaken=True)
        actions.append({"type": "meditation_cycle", "cycle_id": cycle.get("id", ""), "final_state": cycle.get("state", "")})
        post_json(
            f"{STATE_URL}/runtime/mind-state",
            {"last_reflection_at": now, "last_meditation_at": now, "updated_at": now},
            timeout=30,
        )
        state = load_runtime_mind_state()

    if force or due_for_cycle(state.get("last_shadow_at"), MIND_SHADOW_INTERVAL_SECONDS):
        shadow = run_shadow_scan(trigger="scheduled_shadow", run_mode="auto")
        post_json(
            f"{STATE_URL}/runtime/mind-state",
            {"last_shadow_at": now, "updated_at": now},
            timeout=30,
        )
        actions.append({"type": "shadow_scan", "report_id": shadow.get("report_id", "")})

    if not actions:
        return {"ok": True, "mode": "idle", "mind_state": load_runtime_mind_state(), "actions": []}
    return {"ok": True, "mode": "scheduled", "actions": actions, "mind_state": load_runtime_mind_state()}


def format_cycle_text(cycle: dict) -> str:
    artifacts = cycle.get("artifacts", {}) if isinstance(cycle.get("artifacts"), dict) else {}
    lines = [
        f"{cycle.get('id', 'cycle-unknown')}:",
        f"- domain: {cycle.get('domain', 'memory')}",
        f"- trigger: {cycle.get('trigger', 'manual')}",
        f"- run mode: {cycle.get('run_mode', 'manual')}",
        f"- state: {cycle.get('state', 'awake')}",
        f"- summary: {cycle.get('summary', '') or 'n/a'}",
        f"- decision: {cycle.get('homeostasis_decision', '') or 'pending'}",
        f"- artifacts: {len(artifacts)}",
    ]
    return "\n".join(lines)
def process_single_proposal(proposal: dict) -> dict:
    proposal_id = str(proposal.get("id", "")).strip() or "proposal-unknown"
    proposal_text = str(proposal.get("text", "")).strip()
    scope = infer_workcell_scope(proposal_text)
    workcell_dir = WORKCELLS_DIR / proposal_id
    workcell_dir.mkdir(parents=True, exist_ok=True)
    write_workcell_file(workcell_dir, "proposal.json", json.dumps(proposal, indent=2, ensure_ascii=True) + "\n")

    capability_record = record_pending_wish(proposal_id=proposal_id, text=proposal_text)
    plan = post_json(
        f"{BRAIN_URL}/workcell/plan",
        {
            "scope": scope,
            "complexity_class": proposal.get("complexity_class", "medium"),
        },
        timeout=30,
    )
    write_workcell_file(workcell_dir, "plan.json", json.dumps(plan, indent=2, ensure_ascii=True) + "\n")

    target_relpath = safe_generated_relative_path(proposal_id, proposal_text, scope)
    context_bundle = build_context_bundle(scope, proposal_text)
    write_workcell_file(workcell_dir, "context.txt", context_bundle + ("\n" if context_bundle else ""))

    roles = plan.get("roles", [])
    if len(roles) < 2:
        raise RuntimeError("brain workcell plan is incomplete")

    draft_role = roles[0]
    critique_role = roles[1]

    draft_prompt = build_workcell_prompt(
        role_name="draft",
        proposal=proposal,
        scope=scope,
        target_relpath=target_relpath,
        context_bundle=context_bundle,
    )
    draft_run = workcell_role(
        proposal_id=proposal_id,
        role_name="draft",
        prompt_text=draft_prompt,
        task_class=str(draft_role.get("task_class", "chat")),
        complexity_class=str(draft_role.get("complexity_class", proposal.get("complexity_class", "medium"))),
        privacy_class=str(draft_role.get("privacy_class", "internal")),
        frontier_allowed=bool(draft_role.get("frontier_allowed", False)),
    )
    draft_text = str(draft_run["provider_result"].get("response_text", "")).strip()
    draft_content = extract_fenced_content(draft_text, preferred_language="python" if scope == "tests" else "md")
    write_workcell_file(workcell_dir, "draft.run.json", json.dumps(draft_run, indent=2, ensure_ascii=True) + "\n")
    write_workcell_file(workcell_dir, "draft.raw.txt", draft_text + ("\n" if draft_text else ""))
    write_workcell_file(workcell_dir, "draft.content", draft_content + ("\n" if draft_content else ""))

    critique_prompt = build_workcell_prompt(
        role_name="critique",
        proposal=proposal,
        scope=scope,
        target_relpath=target_relpath,
        context_bundle=context_bundle,
        draft_content=draft_content,
    )
    critique_run = workcell_role(
        proposal_id=proposal_id,
        role_name="critique",
        prompt_text=critique_prompt,
        task_class=str(critique_role.get("task_class", "reflect")),
        complexity_class=str(critique_role.get("complexity_class", proposal.get("complexity_class", "medium"))),
        privacy_class=str(critique_role.get("privacy_class", "internal")),
        frontier_allowed=bool(critique_role.get("frontier_allowed", False)),
    )
    critique_text = str(critique_run["provider_result"].get("response_text", "")).strip()
    critique = parse_critique_report(critique_text)
    write_workcell_file(workcell_dir, "critique.run.json", json.dumps(critique_run, indent=2, ensure_ascii=True) + "\n")
    write_workcell_file(workcell_dir, "critique.raw.txt", critique_text + ("\n" if critique_text else ""))
    write_workcell_file(workcell_dir, "critique.json", json.dumps(critique, indent=2, ensure_ascii=True) + "\n")

    safe_scope = scope in {"docs", "tests"}
    frontier_review_required = bool(proposal.get("frontier_review_required", False))
    safe_auto_apply_signal = bool(critique.get("safe_auto_apply")) or bool(
        critique.get("approved") and not critique.get("issues")
    )
    safe_auto_apply = bool(
        safe_scope
        and not frontier_review_required
        and critique.get("approved")
        and safe_auto_apply_signal
        and draft_content.strip()
    )

    if safe_auto_apply:
        apply_result = apply_generated_output(target_relpath=target_relpath, content=draft_content)
        write_workcell_file(workcell_dir, "apply.json", json.dumps(apply_result, indent=2, ensure_ascii=True) + "\n")
        if apply_result["ok"]:
            updated = update_proposal_record(
                proposal_id,
                {
                    "status": "applied_safe",
                    "workcell_scope": scope,
                    "target_path": apply_result["target_path"],
                    "workcell_dir": str(workcell_dir),
                    "summary": critique.get("summary", ""),
                    "capability_gap": capability_record.get("capability_gap", ""),
                },
            )
            return {
                "proposal_id": proposal_id,
                "status": "applied_safe",
                "scope": scope,
                "target_path": apply_result["target_path"],
                "summary": critique.get("summary", ""),
                "proposal": updated.get("proposal", {}),
            }

        updated = update_proposal_record(
            proposal_id,
            {
                "status": "failed_checks",
                "workcell_scope": scope,
                "workcell_dir": str(workcell_dir),
                "summary": critique.get("summary", ""),
                "checks_output": truncate_text(
                    apply_result["checks_result"].get("stdout") or apply_result["checks_result"].get("stderr") or "",
                    limit=2000,
                ),
                "capability_gap": capability_record.get("capability_gap", ""),
            },
        )
        return {
            "proposal_id": proposal_id,
            "status": "failed_checks",
            "scope": scope,
            "summary": critique.get("summary", ""),
            "proposal": updated.get("proposal", {}),
        }

    updated = update_proposal_record(
        proposal_id,
        {
            "status": "draft_ready" if critique.get("approved") else "draft_needs_review",
            "workcell_scope": scope,
            "workcell_dir": str(workcell_dir),
            "target_path": target_relpath if safe_scope else "",
            "summary": critique.get("summary", ""),
            "issues": critique.get("issues", []),
            "capability_gap": capability_record.get("capability_gap", ""),
        },
    )
    return {
        "proposal_id": proposal_id,
        "status": updated.get("proposal", {}).get("status", "draft_ready"),
        "scope": scope,
        "target_path": target_relpath if safe_scope else "",
        "summary": critique.get("summary", ""),
        "proposal": updated.get("proposal", {}),
    }


def process_confirmed_queue(*, limit: int = 3, proposal_id: str = "") -> dict:
    queue_result = list_proposals(limit=max(limit * 4, 10))
    records = queue_result.get("records", [])
    if proposal_id:
        records = [record for record in records if str(record.get("id", "")) == proposal_id]
    else:
        records = [record for record in records if is_runnable_workcell_record(record)]
    records = sorted(records, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))
    processed: list[dict] = []
    for record in records[:limit]:
        proposal_id = str(record.get("id", ""))
        if is_stale_processing_record(record):
            update_proposal_record(
                proposal_id,
                {
                    "status": "retry",
                    "summary": f"Recovered stale processing proposal after {WORKCELL_STALE_SECONDS}s without completion.",
                },
            )
            append_control_log(
                event="proposal_processing_recovered",
                payload={
                    "source": record.get("source", "control"),
                    "user_id": record.get("user_id", ""),
                    "chat_id": record.get("chat_id", ""),
                },
                command="process-queue",
                details={"proposal_id": proposal_id},
            )
        update_proposal_record(proposal_id, {"status": "processing"})
        append_control_log(
            event="proposal_processing_started",
            payload={
                "source": record.get("source", "control"),
                "user_id": record.get("user_id", ""),
                "chat_id": record.get("chat_id", ""),
            },
            command="process-queue",
            details={"proposal_id": proposal_id},
        )
        try:
            outcome = process_single_proposal(record)
        except Exception as exc:
            update_proposal_record(
                proposal_id,
                {
                    "status": "failed_processing",
                    "summary": str(exc),
                },
            )
            outcome = {
                "proposal_id": proposal_id,
                "status": "failed_processing",
                "scope": infer_workcell_scope(str(record.get("text", ""))),
                "summary": str(exc),
            }
        processed.append(outcome)
    return {"ok": True, "processed": processed, "total_processed": len(processed)}


def select_provider_plan(
    *,
    task: str,
    task_class: str,
    source: str,
    original_privacy_class: str,
    provider_override: str,
    complexity_class: str,
) -> tuple[dict, str, str]:
    provider_privacy_class = original_privacy_class
    privacy_fallback_reason = ""

    try:
        provider_plan = post_json(
            f"{BRAIN_URL}/rank",
            {
                "task": task,
                "task_class": task_class,
                "privacy_class": provider_privacy_class,
                "provider": provider_override,
                "complexity_class": complexity_class,
            },
        )
        return provider_plan, provider_privacy_class, privacy_fallback_reason
    except urllib.error.HTTPError as exc:
        error_message = http_error_message(exc)
        if not should_try_private_chat_external_fallback(
            task=task,
            task_class=task_class,
            source=source,
            original_privacy_class=original_privacy_class,
            error_message=error_message,
        ):
            raise RuntimeError(error_message) from exc

    provider_privacy_class = "internal"
    privacy_fallback_reason = (
        "Frontier was unavailable for a private Telegram chat, so Genie downgraded provider privacy "
        "to internal and used the trusted-external lane without sending private memory."
    )
    try:
        provider_plan = post_json(
            f"{BRAIN_URL}/rank",
            {
                "task": task,
                "task_class": task_class,
                "privacy_class": provider_privacy_class,
                "provider": provider_override,
                "complexity_class": complexity_class,
            },
        )
        return provider_plan, provider_privacy_class, privacy_fallback_reason
    except urllib.error.HTTPError as exc:
        raise RuntimeError(http_error_message(exc)) from exc


def execute_task(payload: dict, *, dispatch_mode: bool) -> dict:
    args = namespace_from_payload(payload)
    if not args.task.strip():
        raise RuntimeError("task is required")

    original_privacy_class = (args.privacy_class or "internal").strip().lower() or "internal"
    complexity_class = (args.complexity_class or "medium").strip().lower() or "medium"
    route = local_agent.route_task(args.task)
    provider_plan, provider_privacy_class, privacy_fallback_reason = select_provider_plan(
        task=args.task,
        task_class=args.task_class,
        source=args.source,
        original_privacy_class=original_privacy_class,
        provider_override=args.provider,
        complexity_class=complexity_class,
    )
    context_result = post_json(
        f"{STATE_URL}/context",
        {
            "query": args.task,
            "limit": args.limit,
            "allowed_privacy": allowed_privacy_for_provider(provider_privacy_class),
        },
    )
    hits_result = post_json(
        f"{STATE_URL}/search",
        {
            "query": args.task,
            "limit": args.limit,
            "allowed_privacy": allowed_privacy_for_provider(provider_privacy_class),
        },
    )

    local_summary = "SKIPPED_LOCAL_SUMMARY"
    local_extract = "SKIPPED_LOCAL_EXTRACT"
    if route["label"] == "LOCAL":
        local_summary = local_agent.summarize_text(args.task)
        local_extract = local_agent.extract_text(args.task)

    if args.store:
        memory_source_text = args.memory_text if args.memory_text else args.task
        ingest_result = post_json(
            f"{STATE_URL}/ingest",
            {
                "channel": "ethics",
                "session_id": "execute",
                "role": "user",
                "source": args.source,
                "kind": args.kind,
                "text": memory_source_text,
                "tags": args.tags,
                "privacy_class": original_privacy_class,
            },
        )
        memory_id = ingest_result.get("memory_id", "")
    else:
        memory_id = ""

    remote_package = local_agent.build_remote_package(
        task=args.task,
        route=route,
        local_summary=local_summary,
        local_extract=local_extract,
        memory_context=context_result.get("context", ""),
    )
    package_path = local_agent.save_package(remote_package)

    result = {
        "route": route,
        "provider_plan": provider_plan,
        "original_privacy_class": original_privacy_class,
        "provider_privacy_class": provider_privacy_class,
        "complexity_class": complexity_class,
        "privacy_fallback_reason": privacy_fallback_reason,
        "stored_memory_id": memory_id,
        "remote_package_path": package_path,
        "memory_hits": hits_result.get("results", []),
        "local_summary": local_summary,
        "local_extract": local_extract,
        "memory_context": context_result.get("context", ""),
    }

    if dispatch_mode:
        provider_result = post_json(
            f"{BRAIN_URL}/execute",
            {
                "package_path": package_path,
                "instructions": local_agent.default_gateway_instructions(),
                "provider_plan": provider_plan,
            },
            timeout=300,
        )
        result["provider_response_text"] = provider_result.get("response_text", "")
        result["provider_response_json_path"] = provider_result.get("response_json_path", "")
        result["provider_response_text_path"] = provider_result.get("response_text_path", "")
        result["gateway_response_text"] = provider_result.get("response_text", "")
        result["gateway_response_json_path"] = provider_result.get("response_json_path", "")
        result["gateway_response_text_path"] = provider_result.get("response_text_path", "")
        result["usage"] = provider_result.get("usage", {})
        result["estimated_cost_usd"] = provider_result.get("estimated_cost_usd", 0)
        result["usage_log_path"] = provider_result.get("usage_log_path", "")
        result["provider_id"] = provider_result.get("provider_id", "")
        result["provider_kind"] = provider_result.get("provider_kind", "")
        result["provider_model"] = provider_result.get("provider_model", "")
        result["failovers"] = provider_result.get("failovers", [])
        result["output_assessment"] = provider_result.get("output_assessment", {})

    return result


def handle_control_command(payload: dict, command: dict) -> dict:
    command_name = command["command"]
    argument = command["argument"]
    maybe_refresh_capability_registry()
    instinct = instinct_evaluate({**payload, "task": argument or payload.get("task", "")}, command_name=command_name)

    if not instinct.get("hard_constraints_pass", True) or instinct.get("action_mode") == "deny":
        append_control_log(
            event="command_denied",
            payload=payload,
            command=command_name,
            details={"reason": instinct.get("explanation", "")},
        )
        return {
            "provider_response_text": instinct.get("explanation", "I cannot do that."),
            "instinct": instinct,
        }

    if command_name == "help":
        return {"provider_response_text": HELP_TEXT, "instinct": instinct}

    if command_name == "status":
        return {"provider_response_text": summarize_status_text(), "instinct": instinct}

    if command_name == "policy":
        return {"provider_response_text": summarize_policy_text(), "instinct": instinct}

    if command_name == "brain":
        return {"provider_response_text": summarize_brain_text(), "instinct": instinct}

    if command_name == "state":
        return {"provider_response_text": summarize_state_text(), "instinct": instinct}

    if command_name == "mind":
        return {"provider_response_text": format_mind_text(), "instinct": instinct}

    if command_name == "capabilities":
        return {"provider_response_text": summarize_capabilities_text(), "instinct": instinct}

    if command_name == "meditate":
        domain = (argument or MIND_DEFAULT_DOMAIN).strip().lower() or MIND_DEFAULT_DOMAIN
        if domain != MIND_DEFAULT_DOMAIN:
            return {
                "provider_response_text": f"Unsupported meditation domain: {domain}. Current supported domain: {MIND_DEFAULT_DOMAIN}.",
                "instinct": instinct,
            }
        cycle = create_mind_cycle_record(
            domain=domain,
            trigger="telegram_meditate",
            run_mode="manual",
            state="reflection",
            summary=f"manual meditation requested for {domain}",
        )
        cycle = advance_cycle(cycle, until_states={"sleep", "awake", "recovery"}, auto_sleep=False, auto_awaken=False)
        return {
            "provider_response_text": "Meditation cycle prepared.\n" + format_cycle_text(cycle),
            "instinct": instinct,
            "cycle": cycle,
        }

    if command_name == "homeostasis":
        cycle = resolve_cycle_record(argument or "latest")
        if str(cycle.get("state", "")) in {"reflection", "meditation", "homeostasis_review"}:
            cycle = advance_cycle(cycle, until_states={"sleep", "awake", "recovery"}, auto_sleep=False, auto_awaken=False)
        artifact_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "homeostasis.json"
        review = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.exists() else {}
        reply = format_cycle_text(cycle)
        if review:
            reply += "\n" + "\n".join(
                [
                    f"- homeostasis decision: {review.get('decision', 'unknown')}",
                    f"- protected scope: {review.get('protected_scope', False)}",
                    f"- frontier review required: {review.get('frontier_review_required', False)}",
                ]
            )
            reasons = review.get("reasons", [])
            if reasons:
                reply += "\n- reasons: " + "; ".join(str(item) for item in reasons[:4])
        return {"provider_response_text": reply, "instinct": instinct, "cycle": cycle, "review": review}

    if command_name == "sleep":
        cycle = resolve_cycle_record(argument or "latest")
        cycle = advance_cycle(
            cycle,
            until_states={"awakening_verification", "awake", "recovery"},
            auto_sleep=True,
            auto_awaken=False,
        )
        sleep_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "sleep.json"
        sleep_artifact = json.loads(sleep_path.read_text(encoding="utf-8")) if sleep_path.exists() else {}
        reply = "Sleep integration complete.\n" + format_cycle_text(cycle)
        if sleep_artifact:
            checkpoint_id = sleep_artifact.get("sleep_result", {}).get("checkpoint_id", "")
            if checkpoint_id:
                reply += f"\n- checkpoint: {checkpoint_id}"
        return {"provider_response_text": reply, "instinct": instinct, "cycle": cycle, "sleep": sleep_artifact}

    if command_name == "awaken":
        cycle = resolve_cycle_record(argument or "latest")
        cycle = advance_cycle(cycle, until_states={"awake", "recovery"}, auto_sleep=True, auto_awaken=True)
        awakening_path = cycle_artifact_dir(str(cycle.get("id", ""))) / "awakening.json"
        awakening = json.loads(awakening_path.read_text(encoding="utf-8")) if awakening_path.exists() else {}
        reply = "Awakening verification complete.\n" + format_cycle_text(cycle)
        if awakening:
            reply += f"\n- awakening verdict: {awakening.get('verdict', 'unknown')}"
            anomalies = awakening.get("anomalies", [])
            if anomalies:
                reply += "\n- anomalies: " + "; ".join(str(item) for item in anomalies[:4])
        return {"provider_response_text": reply, "instinct": instinct, "cycle": cycle, "awakening": awakening}

    if command_name == "shadow":
        result = run_shadow_scan(trigger="telegram_shadow", run_mode="manual")
        reply = "\n".join(
            [
                "Shadow scan complete.",
                f"- report: {result.get('report_id', '')}",
                f"- top candidate: {result.get('top_candidate', {}).get('path', 'none')}",
                f"- summary: {result.get('summary', '') or 'n/a'}",
            ]
        )
        return {"provider_response_text": reply, "instinct": instinct, "shadow": result}

    if command_name == "queue":
        queue_result = list_proposals(limit=10)
        return {
            "provider_response_text": format_queue(queue_result.get("records", [])),
            "instinct": instinct,
            "queue": queue_result,
        }

    if command_name == "confirm":
        if not argument:
            return {"provider_response_text": "Usage: /confirm <proposal-id>", "instinct": instinct}
        confirmed = confirm_proposal(argument, payload)
        proposal = confirmed.get("proposal", {})
        if should_process_inline(proposal):
            process_result = process_confirmed_queue(limit=1, proposal_id=str(proposal.get("id", argument)))
            processing_text = format_processing_reply(process_result)
        else:
            process_result = {"ok": True, "processed": [], "total_processed": 0, "deferred": True}
            processing_text = (
                "Queued for background workcell processing. "
                "Use /process-queue or wait for the cron worker if you want the heavier proposal processed."
            )
        return {
            "provider_response_text": (
                f"Confirmed {proposal.get('id', argument)}. "
                f"status={proposal.get('status', 'confirmed')} "
                f"frontier_review_required={proposal.get('frontier_review_required', False)}\n"
                f"{processing_text}"
            ),
            "instinct": instinct,
            "proposal": proposal,
            "process_result": process_result,
        }

    if command_name == "propose":
        if not argument:
            return {"provider_response_text": "Usage: /propose <change request>", "instinct": instinct}
        proposal = create_proposal({**payload, "task": argument}, instinct).get("proposal", {})
        return {
            "provider_response_text": (
                f"Queued {proposal.get('id', 'proposal-unknown')} "
                f"risk={proposal.get('risk_class', 'unknown')} "
                f"complexity={proposal.get('complexity_class', 'medium')} "
                f"frontier_review_required={proposal.get('frontier_review_required', False)}"
            ),
            "instinct": instinct,
            "proposal": proposal,
        }

    if command_name == "backup":
        result = run_local_command(["bash", BACKUP_SCRIPT, "save", "hourly"], timeout=600)
        append_control_log(event="backup_run", payload=payload, command=command_name, details=result)
        if result["ok"]:
            reply = f"Backup saved: {result['stdout'].splitlines()[-1] if result['stdout'] else 'ok'}"
        else:
            reply = f"Backup failed ({result['returncode']}): {truncate_text(result['stderr'] or result['stdout'])}"
        return {"provider_response_text": reply, "instinct": instinct, "command_result": result}

    if command_name == "run-checks":
        result = run_local_command(["bash", CHECKS_SCRIPT], timeout=600)
        append_control_log(event="checks_run", payload=payload, command=command_name, details=result)
        output = result["stdout"] or result["stderr"] or "No output."
        prefix = "Checks passed.\n" if result["ok"] else f"Checks failed ({result['returncode']}).\n"
        return {
            "provider_response_text": prefix + truncate_text(output, limit=2200),
            "instinct": instinct,
            "command_result": result,
        }

    if command_name == "process-queue":
        result = process_confirmed_queue(limit=3)
        append_control_log(event="queue_processed", payload=payload, command=command_name, details=result)
        return {
            "provider_response_text": format_processing_reply(result),
            "instinct": instinct,
            "process_result": result,
        }

    return {"provider_response_text": f"Unknown command: /{command_name}", "instinct": instinct}


def governed_reply(payload: dict) -> dict:
    payload = dict(payload)
    payload.setdefault("task_class", "chat")
    payload.setdefault("privacy_class", "private")
    payload.setdefault("source", "telegram")
    payload.setdefault("kind", "conversation")

    command = parse_control_command(str(payload.get("task", "")))
    if command is not None:
        return handle_control_command(payload, command)

    instinct = instinct_evaluate(payload)
    if not instinct.get("hard_constraints_pass", True) or instinct.get("action_mode") == "deny":
        append_control_log(
            event="reply_denied",
            payload=payload,
            details={"reason": instinct.get("explanation", "")},
        )
        return {"provider_response_text": instinct.get("explanation", "I cannot do that."), "instinct": instinct}

    payload["complexity_class"] = instinct.get("complexity_class", "medium")
    result = execute_task(payload, dispatch_mode=True)
    result["instinct"] = instinct
    result["frontier_review_required"] = instinct.get("frontier_review_required", False)
    return result


def governed_execute(payload: dict) -> dict:
    payload = dict(payload)
    instinct = instinct_evaluate(payload)
    if not instinct.get("hard_constraints_pass", True) or instinct.get("action_mode") == "deny":
        raise RuntimeError(instinct.get("explanation", "Request denied by instinct"))
    payload.setdefault("complexity_class", instinct.get("complexity_class", "medium"))
    result = execute_task(payload, dispatch_mode=bool(payload.get("dispatch", False)))
    result["instinct"] = instinct
    result["frontier_review_required"] = instinct.get("frontier_review_required", False)
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "GenieEthics/0.1"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, indent=2, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        try:
            if self.path == "/health":
                self._write_json(HTTPStatus.OK, {"status": "ok", "service": "ethics"})
                return

            if self.path == "/policy":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "policy": get_text_policy(),
                        "constitution": summarize_policy_text(),
                    },
                )
                return

            if self.path == "/capabilities":
                self._write_json(HTTPStatus.OK, {"capabilities": summarize_capabilities_text()})
                return

            if self.path == "/mind":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "mind_state": load_runtime_mind_state(),
                        "latest_cycles": list_mind_cycles_records(limit=5),
                        "summary": format_mind_text(),
                    },
                )
                return

            if self.path == "/mind/cycles":
                self._write_json(HTTPStatus.OK, {"records": list_mind_cycles_records(limit=20)})
                return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except Exception as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
            return

        try:
            if self.path == "/execute":
                result = governed_execute(payload)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/reply":
                result = governed_reply(payload)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/process-queue":
                result = process_confirmed_queue(
                    limit=max(1, min(10, int(payload.get("limit", 3) or 3))),
                    proposal_id=str(payload.get("proposal_id", "")).strip(),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/mind/run":
                result = run_unattended_cycle(force=bool(payload.get("force", False)))
                self._write_json(HTTPStatus.OK, result)
                return
        except urllib.error.HTTPError as exc:
            self._write_json(HTTPStatus.BAD_GATEWAY, {"error": http_error_message(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ethics listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
