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
MEMORY_URL = os.environ.get("GENIE_MEMORY_URL", "http://127.0.0.1:18792").rstrip("/")
BRAIN_URL = os.environ.get("GENIE_BRAIN_URL", "http://127.0.0.1:18793").rstrip("/")


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def execute_task(payload: dict, *, dispatch_mode: bool) -> dict:
    args = namespace_from_payload(payload)
    if not args.task.strip():
        raise RuntimeError("task is required")

    route = local_agent.route_task(args.task)
    context_result = post_json(
        f"{MEMORY_URL}/context",
        {
            "query": args.task,
            "limit": args.limit,
            "allowed_privacy": ["public", "internal", "private"],
        },
    )
    hits_result = post_json(
        f"{MEMORY_URL}/search",
        {
            "query": args.task,
            "limit": args.limit,
            "allowed_privacy": ["public", "internal", "private"],
        },
    )
    provider_plan = post_json(
        f"{BRAIN_URL}/rank",
        {
            "task": args.task,
            "task_class": args.task_class,
            "privacy_class": args.privacy_class,
            "provider": args.provider,
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
            f"{MEMORY_URL}/ingest",
            {
                "channel": "ethics",
                "session_id": "execute",
                "role": "user",
                "source": args.source,
                "kind": args.kind,
                "text": memory_source_text,
                "tags": args.tags,
                "privacy_class": args.privacy_class,
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
            self._write_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
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
