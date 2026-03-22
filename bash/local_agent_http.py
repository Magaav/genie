#!/usr/bin/env python3

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import local_agent


HOST = os.environ.get("LOCAL_AGENT_HTTP_HOST", "0.0.0.0")
PORT = int(os.environ.get("LOCAL_AGENT_HTTP_PORT", "18790"))


def namespace_from_payload(payload: dict) -> argparse.Namespace:
    return argparse.Namespace(
        task=payload.get("task", ""),
        limit=int(payload.get("limit", 3)),
        store=bool(payload.get("store", False)),
        kind=payload.get("kind", "note"),
        source=payload.get("source", "session"),
        tags=payload.get("tags", "local,agent"),
        memory_text=payload.get("memory_text", ""),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "FreewillerLocalAgent/0.1"

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
        if self.path == "/health":
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

        if self.path == "/policy":
            try:
                output = local_agent.run_command([str(local_agent.LOCAL_LLM_SH), "policy"])
                self._write_json(HTTPStatus.OK, {"policy": output})
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

        task = payload.get("task", "").strip()
        if not task:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "task is required"})
            return

        args = namespace_from_payload(payload)

        try:
            if self.path == "/orchestrate":
                result = local_agent.execute_orchestration(args)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/dispatch":
                result = local_agent.execute_orchestration(args)
                gateway_result = local_agent.dispatch_to_gateway(
                    result["remote_package_path"],
                    instructions=local_agent.default_gateway_instructions(),
                )
                result["gateway_response_text"] = gateway_result["response_text"]
                result["gateway_response_json_path"] = gateway_result["response_json_path"]
                result["gateway_response_text_path"] = gateway_result["response_text_path"]
                self._write_json(HTTPStatus.OK, result)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except RuntimeError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
