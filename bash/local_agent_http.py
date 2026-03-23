#!/usr/bin/env python3

import argparse
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import local_agent
import local_memory
import openclaw_memory_bridge


HOST = os.environ.get("LOCAL_AGENT_HTTP_HOST", "0.0.0.0")
PORT = int(os.environ.get("LOCAL_AGENT_HTTP_PORT", "18790"))


def namespace_from_payload(payload: dict) -> argparse.Namespace:
    return argparse.Namespace(
        task=payload.get("task", ""),
        limit=int(payload.get("limit", 3)),
        store=coerce_bool(payload.get("store", False)),
        kind=payload.get("kind", "note"),
        source=payload.get("source", "session"),
        tags=payload.get("tags", "local,agent"),
        memory_text=payload.get("memory_text", ""),
        task_class=payload.get("task_class", ""),
        privacy_class=payload.get("privacy_class", ""),
        provider=payload.get("provider", ""),
    )


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class Handler(BaseHTTPRequestHandler):
    server_version = "FreewillerLocalAgent/0.2"

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
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "freewiller-local-agent-http",
                    "host": HOST,
                    "port": PORT,
                },
            )
            return

        if parsed.path == "/policy":
            try:
                output = local_agent.run_command([str(local_agent.LOCAL_LLM_SH), "policy"])
                self._write_json(HTTPStatus.OK, {"policy": output})
            except Exception as exc:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if parsed.path == "/providers":
            try:
                self._write_json(
                    HTTPStatus.OK,
                    local_agent.provider_router.public_policy_view(local_agent.provider_router.load_router_config()),
                )
            except Exception as exc:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if parsed.path == "/providers/ranking":
            try:
                task = query.get("task", [""])[0]
                task_class = query.get("task_class", [""])[0]
                privacy_class = query.get("privacy_class", ["public"])[0]
                provider = query.get("provider", [""])[0]
                ranking = local_agent.provider_router.choose_provider(
                    task or task_class or "chat",
                    task_class=task_class,
                    privacy_class=privacy_class,
                    provider_override=provider,
                )
                self._write_json(HTTPStatus.OK, ranking)
            except Exception as exc:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if parsed.path == "/providers/health":
            try:
                refresh = query.get("refresh", ["0"])[0].strip().lower() in {"1", "true", "yes", "on"}
                provider = query.get("provider", [""])[0]
                if refresh:
                    self._write_json(HTTPStatus.OK, local_agent.provider_router.heartbeat_providers(provider_id=provider))
                else:
                    self._write_json(HTTPStatus.OK, local_agent.provider_router.health_public_view())
            except Exception as exc:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if parsed.path == "/memory/stats":
            try:
                self._write_json(HTTPStatus.OK, local_memory.memory_stats())
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
            if self.path == "/memory/ingest":
                text = payload.get("text", "").strip()
                if not text:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "text is required"})
                    return
                result = local_memory.ingest_event(
                    channel=payload.get("channel", "http"),
                    session_id=payload.get("session_id", ""),
                    role=payload.get("role", "user"),
                    user_id=str(payload.get("user_id", "")),
                    source=payload.get("source", "http"),
                    kind=payload.get("kind", "event"),
                    text=text,
                    tags=local_memory.normalize_tags(payload.get("tags", [])),
                    metadata=local_memory.normalize_metadata(payload.get("metadata", {})),
                    derive_memory=not coerce_bool(payload.get("skip_memory", False)),
                    trust_class=str(payload.get("trust_class", "")),
                    privacy_class=str(payload.get("privacy_class", "")),
                    source_type=str(payload.get("source_type", "")),
                    source_id=str(payload.get("source_id", "")),
                    source_provider=str(payload.get("source_provider", "")),
                    source_model=str(payload.get("source_model", "")),
                    verification_status=str(payload.get("verification_status", "")),
                    operator_confirmed=coerce_bool(payload.get("operator_confirmed", False)),
                    policy_tags=local_memory.normalize_policy_tags(payload.get("policy_tags", [])),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/memory/search":
                query = payload.get("query", "").strip()
                if not query:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "query is required"})
                    return
                limit = int(payload.get("limit", 5))
                self._write_json(HTTPStatus.OK, {"results": local_memory.search_memory_entries(query, limit)})
                return

            if self.path == "/memory/context":
                query = payload.get("query", "").strip()
                if not query:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "query is required"})
                    return
                limit = int(payload.get("limit", 5))
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "context": local_memory.build_context(query, limit),
                        "hits": local_memory.search_memory_entries(query, limit),
                    },
                )
                return

            if self.path == "/providers/evaluate":
                result = local_agent.provider_router.evaluate_providers(
                    provider_id=str(payload.get("provider", "")),
                    profile_name=str(payload.get("profile", "")),
                    judge_mode=str(payload.get("judge_mode", "targeted")),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            task = payload.get("task", "").strip()
            if not task:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "task is required"})
                return

            args = namespace_from_payload(payload)

            if self.path == "/orchestrate":
                result = local_agent.execute_orchestration(args)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/dispatch":
                result = local_agent.execute_orchestration(args)
                provider_result = local_agent.dispatch_to_provider(
                    result["remote_package_path"],
                    instructions=local_agent.default_gateway_instructions(),
                    provider_plan=result["provider_plan"],
                )
                result["provider_response_text"] = provider_result["response_text"]
                result["provider_response_json_path"] = provider_result["response_json_path"]
                result["provider_response_text_path"] = provider_result["response_text_path"]
                result["gateway_response_text"] = provider_result["response_text"]
                result["gateway_response_json_path"] = provider_result["response_json_path"]
                result["gateway_response_text_path"] = provider_result["response_text_path"]
                result["usage"] = provider_result["usage"]
                result["estimated_cost_usd"] = provider_result["estimated_cost_usd"]
                result["usage_log_path"] = provider_result["usage_log_path"]
                result["provider_id"] = provider_result["provider_id"]
                result["provider_kind"] = provider_result["provider_kind"]
                result["provider_model"] = provider_result["provider_model"]
                result["failovers"] = provider_result["failovers"]
                self._write_json(HTTPStatus.OK, result)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except RuntimeError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def main() -> int:
    queue_stop_event = openclaw_memory_bridge.start_queue_worker()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if isinstance(queue_stop_event, threading.Event):
            queue_stop_event.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
