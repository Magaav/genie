#!/usr/bin/env python3

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine


HOST = os.environ.get("GENIE_INSTINCT_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENIE_INSTINCT_PORT", "18794"))


class Handler(BaseHTTPRequestHandler):
    server_version = "GenieInstinct/0.1"

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
            self._write_json(HTTPStatus.OK, {"status": "ok", "service": "instinct"})
            return
        if self.path == "/constitution":
            self._write_json(
                HTTPStatus.OK,
                {
                    "service": "instinct",
                    "constitution_kernel": engine.CONSTITUTION_KERNEL,
                    "safe_commands": sorted(engine.SAFE_COMMANDS),
                },
            )
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except Exception as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
            return

        if self.path == "/evaluate":
            try:
                self._write_json(HTTPStatus.OK, engine.evaluate(payload))
                return
            except Exception as exc:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"instinct listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
