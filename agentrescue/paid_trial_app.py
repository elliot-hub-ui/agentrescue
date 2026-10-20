"""AgentRescue MCP service with an optional, fixed-price x402 trial.

Payments are off by default. Enabling the test mode accepts Base Sepolia only;
production mode accepts Base mainnet only. Both modes charge exactly $0.01.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from collections import deque
from threading import Lock

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from app import MAX_DIAGNOSIS_CHARS, diagnose

PRICE = "$0.01"
MAINNET = "eip155:8453"
TESTNET = "eip155:84532"
MAX_REQUEST_BYTES = 16_000
MAX_RESPONSE_BYTES = 16_000
WINDOW_SECONDS = 60
MAX_GETS = 60
MAX_POSTS = 20
_gets: deque[float] = deque()
_posts: deque[float] = deque()
_limit_lock = Lock()
_configured = False
_configure_lock = asyncio.Lock()


def payment_settings(env: dict[str, str] | None = None) -> dict[str, str] | None:
    """Return validated payment settings, or None when the paid trial is off."""
    env = os.environ if env is None else env
    enabled = env.get("AGENTRESCUE_X402_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return None

    test_mode = env.get("AGENTRESCUE_X402_TEST_MODE", "").strip() == "1"
    expected_network = TESTNET if test_mode else MAINNET
    network = env.get("AGENTRESCUE_X402_NETWORK", "").strip()
    if network != expected_network:
        mode = "Base Sepolia" if test_mode else "Base mainnet"
        raise RuntimeError(f"Enabled x402 mode requires AGENTRESCUE_X402_NETWORK={expected_network} ({mode})")

    pay_to = env.get("AGENTRESCUE_X402_PAY_TO", "").strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", pay_to) or pay_to.lower() == "0x" + "0" * 40:
        raise RuntimeError("Enabled x402 mode requires a non-zero EVM receiving address")
    return {"network": network, "pay_to": pay_to, "mode": "testnet" if test_mode else "mainnet"}


def _allow(method: str) -> bool:
    now = time.monotonic()
    queue = _gets if method == "GET" else _posts
    maximum = MAX_GETS if method == "GET" else MAX_POSTS
    with _limit_lock:
        while queue and queue[0] <= now - WINDOW_SECONDS:
            queue.popleft()
        if len(queue) >= maximum:
            return False
        queue.append(now)
        return True


class McpTrafficBounds:
    """Bound request size, per-instance request rates and complete responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "")
        if method in {"GET", "POST", "DELETE"} and not _allow(method):
            response = JSONResponse({"error": "rate_limit", "retry_after_seconds": WINDOW_SECONDS}, status_code=429)
            return await response(scope, receive, send)
        if method in {"POST", "DELETE"}:
            headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
            length = headers.get("content-length")
            if length and (not length.isdecimal() or int(length) > MAX_REQUEST_BYTES):
                response = JSONResponse({"error": "payload_too_large"}, status_code=413)
                return await response(scope, receive, send)

            consumed = 0

            original_receive = receive

            async def bounded_receive():
                nonlocal consumed
                message = await original_receive()
                if message["type"] == "http.request":
                    consumed += len(message.get("body", b""))
                    if consumed > MAX_REQUEST_BYTES:
                        raise ValueError("payload_too_large")
                return message

            receive = bounded_receive

        start = None
        body = bytearray()
        overflow = False

        async def bounded_send(message):
            nonlocal start, overflow
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
                if len(body) > MAX_RESPONSE_BYTES:
                    overflow = True
                if message.get("more_body", False):
                    return
                if start is None:
                    return await send(message)
                if overflow:
                    replacement = JSONResponse({"error": "response_too_large"}, status_code=500)
                    return await replacement(scope, receive, send)
                await send(start)
                await send({"type": "http.response.body", "body": bytes(body), "more_body": False})
                return
            await send(message)

        try:
            await self.app(scope, receive, bounded_send)
        except ValueError as exc:
            if str(exc) != "payload_too_large":
                raise
            response = JSONResponse({"error": "payload_too_large"}, status_code=413)
            await response(scope, receive, send)


mcp = FastMCP("AgentRescue", stateless_http=True, json_response=True)


async def _configure_tool() -> None:
    global _configured
    async with _configure_lock:
        if _configured:
            return
        settings = payment_settings()
        paid = None
        if settings:
            from x402 import x402ResourceServer
            from x402.http import FacilitatorConfig, HTTPFacilitatorClient
            from x402.mcp import create_payment_wrapper
            from x402.mechanisms.evm.exact import ExactEvmServerScheme
            from x402.schemas import ResourceConfig, ResourceInfo

            facilitator_url = os.getenv("AGENTRESCUE_X402_FACILITATOR", "https://x402.org/facilitator").strip()
            if facilitator_url not in {"https://x402.org/facilitator"}:
                raise RuntimeError("The paid trial only permits the reviewed x402.org facilitator")
            resource_server = x402ResourceServer(HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url)))
            resource_server.register(settings["network"], ExactEvmServerScheme())
            resource_server.initialize()
            accepts = resource_server.build_payment_requirements(
                ResourceConfig(
                    scheme="exact",
                    network=settings["network"],
                    payTo=settings["pay_to"],
                    price=PRICE,
                    extra={"name": "USDC", "version": "2"},
                )
            )
            paid = create_payment_wrapper(
                resource_server,
                accepts=accepts,
                resource=ResourceInfo(
                    url="mcp://tool/diagnose_failure",
                    description="Bounded HTTP, API, and MCP error diagnosis",
                    mime_type="application/json",
                ),
            )

        description = "Diagnose a sanitized HTTP/API/MCP error."
        if settings:
            description += " Paid trial: exactly $0.01 USDC per successful diagnosis."
        else:
            description += " No charge; the x402 paid trial is disabled."

        async def diagnose_failure(error: str, system: str = "mcp") -> str:
            if not isinstance(error, str) or not error.strip() or len(error) > MAX_DIAGNOSIS_CHARS:
                raise ValueError(f"error must contain 1–{MAX_DIAGNOSIS_CHARS} characters")
            result = diagnose(error, system)
            result["payment"] = {
                "mode": "x402-" + settings["mode"] if settings else "disabled",
                "price_usd": "0.01" if settings else "0.00",
            }
            return json.dumps(result, separators=(",", ":"))

        handler = paid(diagnose_failure) if paid else diagnose_failure
        mcp.tool(name="diagnose_failure", description=description)(handler)
        _configured = True


async def health(request: Request):
    return JSONResponse({"status": "ok", "payments": "enabled" if payment_settings() else "disabled"})


async def llms(request: Request):
    mode = payment_settings()
    price = "Diagnosis calls cost exactly $0.01 USDC through x402." if mode else "The x402 paid trial is currently disabled; no diagnosis payments are collected."
    content = (
        "# AgentRescue\n\n"
        "MCP endpoint: /mcp (Streamable HTTP). Discover tools freely with tools/list.\n"
        "Call diagnose_failure with a sanitized HTTP, API, or MCP error. Advice is read-only.\n"
        f"{price}\n"
        "Requests are limited to 60 GET and 20 POST per minute per instance; request and response bodies are capped at 16 KB.\n"
        "Do not send secrets or personal data.\n"
    )
    return PlainTextResponse(content)


async def home(request: Request):
    mode = payment_settings()
    status = "Payment trial is active: each successful diagnosis costs $0.01 USDC." if mode else "The payment trial is not enabled; no diagnosis charges are collected."
    html = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>AgentRescue</title><main><h1>Safer next steps for failing agents.</h1>"
        "<p>AgentRescue returns bounded, structured recovery guidance for HTTP, API, and MCP failures."
        " It never executes fixes.</p><p>" + status + "</p>"
        "<p>Agents: connect to <code>/mcp</code>. Discovery and tool listing are free.</p>"
        "<p>Send only synthetic or sanitized errors; secret redaction is best-effort.</p></main></html>"
    )
    return HTMLResponse(html)


@contextlib.asynccontextmanager
async def lifespan(app):
    await _configure_tool()
    async with mcp.session_manager.run():
        yield


mcp_app = mcp.streamable_http_app()
app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/llms.txt", llms, methods=["GET"]),
        Route("/", home, methods=["GET"]),
        Mount("/", app=mcp_app),
    ],
    middleware=[Middleware(McpTrafficBounds)],
    lifespan=lifespan,
)
