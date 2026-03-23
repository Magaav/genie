#!/usr/bin/env python3

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import memory_domain
import gateway_domain
import policy_domain
import runtime_domain
import telemetry_domain
from common import STATE_LAYOUT


HOST = os.environ.get("GENIE_STATE_HOST", os.environ.get("GENIE_MEMORY_HOST", "127.0.0.1"))
PORT = int(os.environ.get("GENIE_STATE_PORT", os.environ.get("GENIE_MEMORY_PORT", "18792")))

MEMORY_POST_PATHS = {
    "/ingest": memory_domain.ingest,
    "/memory/ingest": memory_domain.ingest,
    "/state/ingest": memory_domain.ingest,
    "/search": memory_domain.search,
    "/memory/search": memory_domain.search,
    "/state/search": memory_domain.search,
    "/context": memory_domain.context,
    "/memory/context": memory_domain.context,
    "/state/context": memory_domain.context,
    "/sync-projections": lambda payload: memory_domain.sync_projections(),
    "/memory/sync-projections": lambda payload: memory_domain.sync_projections(),
    "/state/sync-projections": lambda payload: memory_domain.sync_projections(),
}


def domains_catalog() -> dict:
    return {
        "service": "state",
        "state_dir": str(STATE_LAYOUT["state_dir"]),
        "domains": {
            "memory": str(STATE_LAYOUT["memory_dir"]),
            "policy": str(STATE_LAYOUT["policy_dir"]),
            "gateway": str(STATE_LAYOUT["gateway_dir"]),
            "telemetry": str(STATE_LAYOUT["telemetry_dir"]),
            "runtime": str(STATE_LAYOUT["runtime_dir"]),
        },
    }


def state_summary() -> dict:
    return {
        "service": "state",
        "state_dir": str(STATE_LAYOUT["state_dir"]),
        "domains": {
            "memory": memory_domain.stats(),
            "policy": policy_domain.summary(),
            "gateway": gateway_domain.summary(),
            "telemetry": telemetry_domain.summary(),
            "runtime": runtime_domain.summary(),
        },
    }


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
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/health":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "state",
                        "domains": sorted(domains_catalog()["domains"]),
                    },
                )
                return

            if parsed.path in {"/domains", "/state/domains"}:
                self._write_json(HTTPStatus.OK, domains_catalog())
                return

            if parsed.path in {"/state/summary"}:
                self._write_json(HTTPStatus.OK, state_summary())
                return

            if parsed.path in {"/stats", "/memory/stats", "/state/stats"}:
                self._write_json(HTTPStatus.OK, memory_domain.stats())
                return

            if parsed.path in {"/policy/summary", "/state/policy/summary"}:
                self._write_json(HTTPStatus.OK, policy_domain.summary())
                return

            if parsed.path in {"/gateway/summary", "/state/gateway/summary"}:
                self._write_json(HTTPStatus.OK, gateway_domain.summary())
                return

            if parsed.path in {"/telemetry/summary", "/state/telemetry/summary"}:
                self._write_json(HTTPStatus.OK, telemetry_domain.summary())
                return

            if parsed.path in {"/runtime/summary", "/state/runtime/summary"}:
                self._write_json(HTTPStatus.OK, runtime_domain.summary())
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
            handler = MEMORY_POST_PATHS.get(self.path)
            if handler is not None:
                self._write_json(HTTPStatus.OK, handler(payload))
                return
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    memory_domain.try_sync_projections()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"state listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
