#!/usr/bin/env python3

import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, "/local/bash")

import local_agent  # noqa: E402
import provider_router  # noqa: E402


HOST = os.environ.get("GENIE_BRAIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENIE_BRAIN_PORT", "18793"))


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class Handler(BaseHTTPRequestHandler):
    server_version = "GenieBrain/0.1"

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

        try:
            if parsed.path == "/health":
                config = provider_router.load_router_config()
                providers = config.get("providers", {})
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "brain",
                        "provider_count": len(providers),
                        "leader_count": sum(
                            1 for provider in providers.values() if provider.get("brain_state") == "leader"
                        ),
                    },
                )
                return

            if parsed.path == "/providers":
                self._write_json(HTTPStatus.OK, provider_router.public_policy_view(provider_router.load_router_config()))
                return

            if parsed.path == "/providers/ranking":
                task = query.get("task", [""])[0]
                task_class = query.get("task_class", [""])[0]
                privacy_class = query.get("privacy_class", ["public"])[0]
                provider = query.get("provider", [""])[0]
                ranking = provider_router.choose_provider(
                    task or task_class or "chat",
                    task_class=task_class,
                    privacy_class=privacy_class,
                    provider_override=provider,
                )
                self._write_json(HTTPStatus.OK, ranking)
                return

            if parsed.path == "/providers/health":
                refresh = query.get("refresh", ["0"])[0].strip().lower() in {"1", "true", "yes", "on"}
                provider = query.get("provider", [""])[0]
                if refresh:
                    self._write_json(HTTPStatus.OK, provider_router.heartbeat_providers(provider_id=provider))
                else:
                    self._write_json(HTTPStatus.OK, provider_router.health_public_view())
                return

            if parsed.path == "/providers/scorecards":
                refresh = query.get("refresh", ["0"])[0].strip().lower() in {"1", "true", "yes", "on"}
                self._write_json(HTTPStatus.OK, provider_router.scorecards_public_view(refresh=refresh))
                return

            if parsed.path == "/providers/discovery":
                self._write_json(HTTPStatus.OK, provider_router.discovery_public_view())
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
            if self.path == "/rank":
                task = str(payload.get("task", "")).strip()
                if not task:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "task is required"})
                    return
                result = provider_router.choose_provider(
                    task,
                    task_class=str(payload.get("task_class", "")),
                    privacy_class=str(payload.get("privacy_class", "")),
                    provider_override=str(payload.get("provider", "")),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/execute":
                package_path = str(payload.get("package_path", "")).strip()
                provider_plan = payload.get("provider_plan")
                if not package_path or not isinstance(provider_plan, dict):
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "package_path and provider_plan are required"},
                    )
                    return
                result = local_agent.dispatch_to_provider(
                    package_path,
                    instructions=str(payload.get("instructions", "")).strip() or None,
                    provider_plan=provider_plan,
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/providers/evaluate":
                result = provider_router.evaluate_providers(
                    provider_id=str(payload.get("provider", "")),
                    profile_name=str(payload.get("profile", "")),
                    judge_mode=str(payload.get("judge_mode", "targeted")),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.path == "/providers/discover":
                result = provider_router.discover_models(
                    provider_family=str(payload.get("provider_family", "nvidia")),
                    sync=coerce_bool(payload.get("sync", True)),
                )
                self._write_json(HTTPStatus.OK, result)
                return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"brain listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
