#!/usr/bin/env python3

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


HOST = os.environ.get("GENIE_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("GENIE_GATEWAY_PORT", "18790"))
ETHICS_URL = os.environ.get("GENIE_ETHICS_URL", "http://127.0.0.1:18791").rstrip("/")
STATE_URL = os.environ.get("GENIE_STATE_URL", os.environ.get("GENIE_MEMORY_URL", "http://127.0.0.1:18792")).rstrip("/")
BRAIN_URL = os.environ.get("GENIE_BRAIN_URL", "http://127.0.0.1:18793").rstrip("/")
STATE_DIR = Path("/local/state/genie")
GATEWAY_STATE_DIR = STATE_DIR / "gateway"
TELEGRAM_OFFSET_FILE = GATEWAY_STATE_DIR / "telegram-update-offset.json"
TELEGRAM_ALLOWLIST_FILE = GATEWAY_STATE_DIR / "telegram-allowlist.json"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or os.environ.get("TELEGRAN_TOKEN", "").strip()
TELEGRAM_POLL_TIMEOUT_SECONDS = int(os.environ.get("TELEGRAM_POLL_TIMEOUT_SECONDS", "30"))
TELEGRAM_ENABLED = os.environ.get("GENIE_TELEGRAM_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def read_json_file(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def http_get_json(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict, timeout: int = 120) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def proxy_get(base_url: str, path: str, query: str = "") -> dict:
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{query}"
    return http_get_json(url)


def proxy_post(base_url: str, path: str, payload: dict, timeout: int = 120) -> dict:
    return http_post_json(f"{base_url}{path}", payload, timeout=timeout)


def telegram_base_url() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def load_allowlist() -> set[str]:
    if not TELEGRAM_ALLOWLIST_FILE.exists():
        raw_env = os.environ.get("TELEGRAM_ALLOW_FROM", "").strip()
        if raw_env:
            return {item.strip() for item in raw_env.split(",") if item.strip()}
        return set()
    payload = read_json_file(TELEGRAM_ALLOWLIST_FILE, {"allow_from": []})
    allow_from = payload.get("allow_from", payload.get("allowFrom", []))
    return {str(item).strip() for item in allow_from if str(item).strip()}


def read_update_offset() -> int:
    payload = read_json_file(TELEGRAM_OFFSET_FILE, {"offset": 0})
    try:
        return max(0, int(payload.get("offset", 0)))
    except (TypeError, ValueError):
        return 0


def write_update_offset(offset: int) -> None:
    write_json_file(TELEGRAM_OFFSET_FILE, {"offset": max(0, int(offset))})


def telegram_api(method: str, payload: dict, timeout: int = 60) -> dict:
    return http_post_json(f"{telegram_base_url()}/{method}", payload, timeout=timeout)


def ingest_telegram_event(
    *,
    role: str,
    user_id: str,
    chat_id: str,
    text: str,
    source: str,
    source_id: str,
    skip_memory: bool = False,
) -> None:
    proxy_post(
        STATE_URL,
        "/ingest",
        {
            "channel": "telegram",
            "session_id": f"telegram:{chat_id}",
            "role": role,
            "user_id": user_id,
            "source": source,
            "kind": "conversation",
            "text": text,
            "tags": ["telegram", "dm"],
            "metadata": {"chat_id": chat_id},
            "skip_memory": skip_memory,
            "trust_class": "untrusted_user_content" if role == "user" else "semi_trusted_internal",
            "privacy_class": "private",
            "source_type": "telegram",
            "source_id": source_id,
            "source_provider": "telegram",
            "verification_status": "unverified" if role == "user" else "derived",
        },
        timeout=120,
    )


def reply_to_telegram_message(message: dict) -> None:
    text = str(message.get("text", "")).strip()
    if not text:
        return

    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_id = str(chat.get("id", ""))
    user_id = str(sender.get("id", ""))
    message_id = str(message.get("message_id", ""))
    allowlist = load_allowlist()
    if allowlist and user_id not in allowlist:
        return

    ingest_telegram_event(
        role="user",
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        source="telegram",
        source_id=message_id,
    )

    result = proxy_post(
        ETHICS_URL,
        "/reply",
        {
            "task": text,
            "limit": 5,
            "task_class": "chat",
            "privacy_class": "private",
            "source": "telegram",
        },
        timeout=300,
    )
    reply_text = str(result.get("provider_response_text", "")).strip() or "I do not have a reply yet."
    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": reply_text,
        },
        timeout=120,
    )
    ingest_telegram_event(
        role="assistant",
        user_id=user_id,
        chat_id=chat_id,
        text=reply_text,
        source="gateway",
        source_id=f"reply:{message_id}",
        skip_memory=False,
    )


def telegram_worker(stop_event: threading.Event) -> None:
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN:
        return

    while not stop_event.is_set():
        offset = read_update_offset()
        try:
            payload = telegram_api(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": TELEGRAM_POLL_TIMEOUT_SECONDS,
                    "allowed_updates": ["message"],
                },
                timeout=TELEGRAM_POLL_TIMEOUT_SECONDS + 10,
            )
            results = payload.get("result", [])
            next_offset = offset
            for update in results:
                update_id = int(update.get("update_id", 0))
                next_offset = max(next_offset, update_id + 1)
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                if chat.get("type") != "private":
                    continue
                reply_to_telegram_message(message)
            if next_offset != offset:
                write_update_offset(next_offset)
        except Exception:
            stop_event.wait(5)


class Handler(BaseHTTPRequestHandler):
    server_version = "GenieGateway/0.1"

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
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "gateway",
                        "identity": "Genie",
                        "telegram_enabled": bool(TELEGRAM_ENABLED and TELEGRAM_TOKEN),
                        "telegram_allowlist_size": len(load_allowlist()),
                    },
                )
                return

            if parsed.path == "/policy":
                self._write_json(HTTPStatus.OK, proxy_get(ETHICS_URL, "/policy"))
                return

            if parsed.path == "/providers":
                self._write_json(HTTPStatus.OK, proxy_get(BRAIN_URL, "/providers", parsed.query))
                return

            if parsed.path == "/providers/ranking":
                self._write_json(HTTPStatus.OK, proxy_get(BRAIN_URL, "/providers/ranking", parsed.query))
                return

            if parsed.path == "/providers/health":
                self._write_json(HTTPStatus.OK, proxy_get(BRAIN_URL, "/providers/health", parsed.query))
                return

            if parsed.path == "/providers/scorecards":
                self._write_json(HTTPStatus.OK, proxy_get(BRAIN_URL, "/providers/scorecards", parsed.query))
                return

            if parsed.path == "/providers/discovery":
                self._write_json(HTTPStatus.OK, proxy_get(BRAIN_URL, "/providers/discovery", parsed.query))
                return

            if parsed.path in {"/memory/stats", "/state/stats"}:
                self._write_json(HTTPStatus.OK, proxy_get(STATE_URL, "/stats"))
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
            if self.path in {"/memory/ingest", "/state/ingest"}:
                self._write_json(HTTPStatus.OK, proxy_post(STATE_URL, "/ingest", payload))
                return

            if self.path in {"/memory/search", "/state/search"}:
                self._write_json(HTTPStatus.OK, proxy_post(STATE_URL, "/search", payload))
                return

            if self.path in {"/memory/context", "/state/context"}:
                self._write_json(HTTPStatus.OK, proxy_post(STATE_URL, "/context", payload))
                return

            if self.path in {"/memory/sync-projections", "/state/sync-projections"}:
                self._write_json(HTTPStatus.OK, proxy_post(STATE_URL, "/sync-projections", payload))
                return

            if self.path == "/providers/evaluate":
                self._write_json(HTTPStatus.OK, proxy_post(BRAIN_URL, "/providers/evaluate", payload, timeout=300))
                return

            if self.path == "/providers/discover":
                self._write_json(HTTPStatus.OK, proxy_post(BRAIN_URL, "/providers/discover", payload, timeout=300))
                return

            if self.path == "/orchestrate":
                payload["dispatch"] = False
                self._write_json(HTTPStatus.OK, proxy_post(ETHICS_URL, "/execute", payload, timeout=300))
                return

            if self.path == "/dispatch":
                payload["dispatch"] = True
                self._write_json(HTTPStatus.OK, proxy_post(ETHICS_URL, "/execute", payload, timeout=300))
                return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def main() -> int:
    GATEWAY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()
    if TELEGRAM_ENABLED and TELEGRAM_TOKEN:
        thread = threading.Thread(target=telegram_worker, args=(stop_event,), name="telegram-worker", daemon=True)
        thread.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"gateway listening on {HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
