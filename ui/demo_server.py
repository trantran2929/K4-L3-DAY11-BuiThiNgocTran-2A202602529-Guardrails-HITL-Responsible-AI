from __future__ import annotations

import asyncio
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.agent import create_blue_agent
from assignment.pipeline import build_production_plugins
from core.config import get_blue_model, get_openrouter_api_key
from core.utils import chat_with_agent

PAGE = UI_DIR / "demo.html"
MAX_MESSAGE_LENGTH = 3000


def make_demo_state() -> dict:
    if not get_openrouter_api_key():
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Add it to the local .env file."
        )

    plugins = build_production_plugins(use_llm_judge=False)
    agent, runner = create_blue_agent(plugins)
    return {
        "agent": agent,
        "runner": runner,
        "plugins": plugins,
        "rate_limiter": next(p for p in plugins if p.name == "rate_limiter"),
        "input_guardrail": next(p for p in plugins if p.name == "input_guardrail"),
        "output_guardrail": next(p for p in plugins if p.name == "output_guardrail"),
    }


STATE = make_demo_state()


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "VinBankDemo/1.0"

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == "/":
            self._send(
                HTTPStatus.OK,
                PAGE.read_bytes(),
                "text/html; charset=utf-8",
            )
            return
        if route == "/api/status":
            self._send_json(HTTPStatus.OK, {
                "ready": True,
                "model": get_blue_model(),
                "provider": "OpenRouter",
            })
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                self._send_json(HTTPStatus.BAD_REQUEST, {
                    "error": "Invalid request size."
                })
                return
            payload = json.loads(self.rfile.read(length))
            message = payload.get("message", "")
            if not isinstance(message, str) or not message.strip():
                self._send_json(HTTPStatus.BAD_REQUEST, {
                    "error": "Enter a message first."
                })
                return
            message = message.strip()
            if len(message) > MAX_MESSAGE_LENGTH:
                self._send_json(HTTPStatus.BAD_REQUEST, {
                    "error": f"Messages are limited to {MAX_MESSAGE_LENGTH} characters."
                })
                return
        except (ValueError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
            return

        rate_limiter = STATE["rate_limiter"]
        input_guardrail = STATE["input_guardrail"]
        output_guardrail = STATE["output_guardrail"]
        before = {
            "rate": rate_limiter.blocked_count,
            "input": input_guardrail.blocked_count,
            "redacted": output_guardrail.redacted_count,
        }

        try:
            response, _ = asyncio.run(
                chat_with_agent(STATE["agent"], STATE["runner"], message)
            )
        except Exception as exc:
            print(f"Chat request failed: {type(exc).__name__}")
            self._send_json(HTTPStatus.BAD_GATEWAY, {
                "error": "The model request failed. Check the server terminal."
            })
            return

        if rate_limiter.blocked_count > before["rate"]:
            layer = "rate_limiter"
            status = "blocked"
        elif input_guardrail.blocked_count > before["input"]:
            layer = "input_guardrail"
            status = "blocked"
        elif output_guardrail.redacted_count > before["redacted"]:
            layer = "output_guardrail"
            status = "redacted"
        else:
            layer = None
            status = "passed"

        self._send_json(HTTPStatus.OK, {
            "reply": response,
            "status": status,
            "layer": layer,
        })


def main() -> None:
    server = None
    for port in range(8765, 8785):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
            break
        except OSError:
            continue

    if server is None:
        raise SystemExit("No available demo port found between 8765 and 8784.")

    print(f"VinBank Guardrail Demo: http://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping demo server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()