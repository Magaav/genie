#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/local/bash")

import local_agent  # noqa: E402
from control_plane import HELP_TEXT, format_queue, parse_control_command  # noqa: E402


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
    runtime = summary.get("domains", {}).get("runtime", {})
    return "\n".join(
        [
            "State:",
            f"- memory entries: {memory.get('semantic_entries', 0)}",
            f"- journal events: {memory.get('journal_events', 0)}",
            f"- blocked promotions: {memory.get('blocked_promotions', 0)}",
            f"- queued proposals: {runtime.get('review_queue_file', {}).get('queued', 0)}",
            f"- confirmed proposals: {runtime.get('review_queue_file', {}).get('confirmed', 0)}",
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
        return {
            "provider_response_text": (
                f"Confirmed {proposal.get('id', argument)}. "
                f"status={proposal.get('status', 'confirmed')} "
                f"frontier_review_required={proposal.get('frontier_review_required', False)}"
            ),
            "instinct": instinct,
            "proposal": proposal,
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
