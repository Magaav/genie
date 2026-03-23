#!/usr/bin/env python3

import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/local/bash")

import local_memory  # noqa: E402


HOST = os.environ.get("GENIE_STATE_HOST", os.environ.get("GENIE_MEMORY_HOST", "127.0.0.1"))
PORT = int(os.environ.get("GENIE_STATE_PORT", os.environ.get("GENIE_MEMORY_PORT", "18792")))


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class Handler(BaseHTTPRequestHandler):
    server_version = "GenieState/0.1"

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
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "state",
                    },
                )
                return

            if self.path == "/stats":
                self._write_json(HTTPStatus.OK, local_memory.memory_stats())
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
            if self.path == "/ingest":
                text = str(payload.get("text", "")).strip()
                if not text:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "text is required"})
                    return
                result = local_memory.ingest_event(
                    channel=str(payload.get("channel", "http")),
                    session_id=str(payload.get("session_id", "")),
                    role=str(payload.get("role", "user")),
                    user_id=str(payload.get("user_id", "")),
                    source=str(payload.get("source", "http")),
                    kind=str(payload.get("kind", "event")),
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

            if self.path == "/search":
                query = str(payload.get("query", "")).strip()
                if not query:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "query is required"})
                    return
                limit = int(payload.get("limit", 5))
                allowed_privacy = payload.get("allowed_privacy")
                self._write_json(
                    HTTPStatus.OK,
                    {"results": local_memory.search_memory_entries(query, limit, allowed_privacy)},
                )
                return

            if self.path == "/context":
                query = str(payload.get("query", "")).strip()
                if not query:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "query is required"})
                    return
                limit = int(payload.get("limit", 5))
                allowed_privacy = payload.get("allowed_privacy")
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "context": local_memory.build_context(query, limit, allowed_privacy),
                        "hits": local_memory.search_memory_entries(query, limit, allowed_privacy),
                    },
                )
                return

            if self.path == "/sync-projections":
                local_memory.sync_projection_files()
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "projection_memory_file": str(local_memory.PROJECTION_MEMORY_FILE),
                    },
                )
                return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    local_memory.try_sync_projection_files()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"state listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
