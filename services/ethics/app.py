#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/local/bash")

import local_agent  # noqa: E402


HOST = os.environ.get("GENIE_ETHICS_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENIE_ETHICS_PORT", "18791"))
STATE_URL = os.environ.get("GENIE_STATE_URL", os.environ.get("GENIE_MEMORY_URL", "http://127.0.0.1:18792")).rstrip("/")
BRAIN_URL = os.environ.get("GENIE_BRAIN_URL", "http://127.0.0.1:18793").rstrip("/")
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


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
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


def select_provider_plan(
    *,
    task: str,
    task_class: str,
    source: str,
    original_privacy_class: str,
    provider_override: str,
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
    route = local_agent.route_task(args.task)
    provider_plan, provider_privacy_class, privacy_fallback_reason = select_provider_plan(
        task=args.task,
        task_class=args.task_class,
        source=args.source,
        original_privacy_class=original_privacy_class,
        provider_override=args.provider,
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
                self._write_json(HTTPStatus.OK, {"policy": get_text_policy()})
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
                result = execute_task(payload, dispatch_mode=bool(payload.get("dispatch", False)))
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/reply":
                payload.setdefault("task_class", "chat")
                payload.setdefault("privacy_class", "private")
                payload.setdefault("source", "telegram")
                payload.setdefault("kind", "conversation")
                result = execute_task(payload, dispatch_mode=True)
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
