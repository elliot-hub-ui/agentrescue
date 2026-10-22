"""AgentRescue MCP service with an optional, fixed-price x402 trial.

Payments are off by default. Enabling the test mode accepts Base Sepolia only;
production mode accepts Base mainnet only. Both modes charge exactly $0.01.
"""
from __future__ import annotations

import asyncio
import copy
import contextlib
import json
import os
import re
import time
from collections import deque
from threading import Lock
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from app import FEEDBACK_CATEGORIES, FEEDBACK_OUTCOMES, MAX_DIAGNOSIS_CHARS, SCHEMA, diagnose

PRICE = "$0.01"
PUBLIC_BASE_URL = "https://agentrescue-mcp.onrender.com"
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
    facilitator_url = env.get("AGENTRESCUE_X402_FACILITATOR", "").strip()
    if test_mode:
        facilitator_url = facilitator_url or "https://x402.org/facilitator"
        parsed = urlparse(facilitator_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "x402.org"
            or parsed.path.rstrip("/") != "/facilitator"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Test mode only permits the HTTPS x402.org facilitator")
    else:
        if env.get("AGENTRESCUE_X402_PRODUCTION_APPROVED", "").strip() != "1":
            raise RuntimeError("Base mainnet payments require AGENTRESCUE_X402_PRODUCTION_APPROVED=1")
        if not facilitator_url:
            raise RuntimeError("Base mainnet payments require an explicitly selected facilitator")
        parsed = urlparse(facilitator_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("Production facilitator must be a clean HTTPS URL without embedded credentials or query data")
        if parsed.hostname.lower() == "x402.org" and parsed.path.rstrip("/") == "/facilitator":
            raise RuntimeError("The public x402.org facilitator is reserved here for testnet use")

    return {
        "network": network,
        "pay_to": pay_to,
        "mode": "testnet" if test_mode else "mainnet",
        "facilitator_url": facilitator_url,
    }


def payment_resource_config(settings: dict[str, str]):
    """Build the payment config using the field names in the pinned x402 SDK."""
    from x402.schemas import ResourceConfig

    return ResourceConfig(
        scheme="exact",
        network=settings["network"],
        pay_to=settings["pay_to"],
        price=PRICE,
        extra={"name": "USDC", "version": "2"},
    )


def http_payment_routes(settings: dict[str, str]) -> dict[str, dict]:
    """Build the single paid HTTP route and its Bazaar JSON discovery schema."""
    from x402.extensions.bazaar import OutputConfig, declare_discovery_extension

    request_schema = {
        "type": "object",
        "properties": {
            "error": {"type": "string", "minLength": 1, "maxLength": MAX_DIAGNOSIS_CHARS},
            "system": {"type": "string", "enum": ["http", "api", "mcp"], "default": "http"},
        },
        "required": ["error"],
        "additionalProperties": False,
    }
    output_schema = copy.deepcopy(SCHEMA["components"]["schemas"]["Diagnosis"])
    output_schema["properties"]["payment"] = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["x402-testnet", "x402-mainnet"]},
            "price_usd": {"type": "string", "const": "0.01"},
        },
        "required": ["mode", "price_usd"],
        "additionalProperties": False,
    }
    discovery = declare_discovery_extension(
        input={"error": "HTTP 429 rate limit", "system": "http"},
        input_schema=request_schema,
        body_type="json",
        output=OutputConfig(
            example={
                "system": "http",
                "category": "rate_limit",
                "summary": "Matched a rate limit failure indicator. Confirm it applies to the latest failing request.",
                "confidence": "medium",
                "confidence_basis": "A deterministic rule matched a known error phrase; this is not a calibrated probability.",
                "recovery": {
                    "guidance": "Honor Retry-After; reduce concurrency and use bounded jittered backoff.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "execute_automatically": False,
                },
                "evidence": {"signals": ["429"], "redacted": False},
                "payment": {
                    "mode": "x402-" + settings["mode"],
                    "price_usd": "0.01",
                },
            },
            schema=output_schema,
        ),
    )
    routes = {
        "POST /v1/diagnose": {
            "accepts": {
                "scheme": "exact",
                "payTo": settings["pay_to"],
                "price": PRICE,
                "network": settings["network"],
                "extra": {"name": "USDC", "version": "2"},
            },
            "resource": PUBLIC_BASE_URL + "/v1/diagnose",
            "description": "Diagnose a sanitized HTTP, API, or MCP failure and return read-only recovery guidance.",
            "mimeType": "application/json",
            "service_name": "AgentRescue",
            "tags": ["diagnostics", "agents"],
            "extensions": discovery,
        }
    }
    return routes


def http_payment_middleware(settings: dict[str, str]):
    """Build the SDK middleware for the paid HTTP diagnosis route."""
    from x402 import x402ResourceServer
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    server = x402ResourceServer(
        HTTPFacilitatorClient(FacilitatorConfig(url=settings["facilitator_url"]))
    )
    server.register(settings["network"], ExactEvmServerScheme())
    return Middleware(PaymentMiddlewareASGI, routes=http_payment_routes(settings), server=server)


def payment_discovery_extension():
    """Describe the paid MCP tool for facilitators that support Bazaar discovery."""
    from x402.extensions.bazaar import (
        DeclareMcpDiscoveryConfig,
        declare_mcp_discovery_extension,
    )

    return declare_mcp_discovery_extension(
        DeclareMcpDiscoveryConfig(
            tool_name="diagnose_failure",
            description="Diagnose a sanitized HTTP, API, or MCP error with read-only recovery guidance.",
            transport="streamable-http",
            input_schema={
                "type": "object",
                "properties": {
                    "error": {"type": "string", "minLength": 1, "maxLength": MAX_DIAGNOSIS_CHARS},
                    "system": {"type": "string", "enum": ["http", "api", "mcp"]},
                },
                "required": ["error"],
                "additionalProperties": False,
            },
            example={"error": "HTTP 429 rate limit", "system": "http"},
        )
    )


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
    """Bound request and response traffic for the public MCP endpoint."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "")
        if method in {"GET", "POST", "DELETE"} and not _allow(method):
            response = JSONResponse({"error": "rate_limit", "retry_after_seconds": WINDOW_SECONDS}, status_code=429)
            return await response(scope, receive, send)
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        request_body = b""
        app_receive = receive
        if method == "POST":
            length = headers.get("content-length")
            if length and (not length.isdecimal() or int(length) > MAX_REQUEST_BYTES):
                response = JSONResponse({"error": "payload_too_large"}, status_code=413)
                return await response(scope, receive, send)
            body_parts = []
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                part = message.get("body", b"")
                total += len(part)
                if total > MAX_REQUEST_BYTES:
                    response = JSONResponse({"error": "payload_too_large"}, status_code=413)
                    return await response(scope, receive, send)
                body_parts.append(part)
                if not message.get("more_body", False):
                    break
            request_body = b"".join(body_parts)
            replayed = False

            async def replay_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": request_body, "more_body": False}
                return await receive()

            app_receive = replay_receive

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

        await self.app(scope, app_receive, bounded_send)

class McpPostRoute(Route):
    """Add 2026 server/discover while proxying supported MCP POSTs to FastMCP."""

    def __init__(self, mcp_app):
        self.mcp_app = mcp_app
        super().__init__("/mcp", self.unused_endpoint, methods=["POST"])

    async def unused_endpoint(self, request: Request):  # pragma: no cover - handle() owns dispatch
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def handle(self, scope, receive, send):
        body_parts = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            part = message.get("body", b"")
            total += len(part)
            if total > MAX_REQUEST_BYTES:
                response = JSONResponse({"error": "payload_too_large"}, status_code=413)
                return await response(scope, receive, send)
            body_parts.append(part)
            if not message.get("more_body", False):
                break
        request_body = b"".join(body_parts)
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        try:
            request_json = json.loads(request_body)
        except (TypeError, ValueError):
            request_json = None
        if isinstance(request_json, dict) and request_json.get("method") == "server/discover":
            await self._discover(scope, headers, request_json, receive, send)
            return

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return await receive()

        await self.mcp_app(scope, replay_receive, send)

    async def _discover(self, scope, headers, request_json, receive, send):
        request_id = request_json.get("id")

        def respond(payload, status=200):
            return JSONResponse(payload, status_code=status)

        def error(code, message, status=200, data=None):
            detail = {"code": code, "message": message}
            if data is not None:
                detail["data"] = data
            return respond({"jsonrpc": "2.0", "id": request_id, "error": detail}, status)

        host = headers.get("host", "")
        allowed_hosts = TransportSecuritySettings(
            allowed_hosts=[
                "agentrescue-mcp.onrender.com", "agentrescue-mcp.onrender.com:*",
                "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*",
            ]
        ).allowed_hosts
        host_ok = host in allowed_hosts or any(
            allowed.endswith(":*") and host.startswith(allowed[:-2] + ":")
            for allowed in allowed_hosts
        )
        if not host_ok:
            return await PlainTextResponse("Invalid Host header", status_code=421)(scope, receive, send)
        origin = headers.get("origin")
        allowed_origins = {
            "https://agentrescue-mcp.onrender.com", "http://localhost", "http://127.0.0.1",
        }
        if origin and origin not in allowed_origins:
            return await PlainTextResponse("Invalid Origin header", status_code=403)(scope, receive, send)

        if request_json.get("jsonrpc") != "2.0" or request_id is None:
            return await error(-32600, "Invalid Request")(scope, receive, send)
        params = request_json.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return await error(-32602, "params must be an object")(scope, receive, send)
        meta = params.get("_meta", {})
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            return await error(-32602, "_meta must be an object")(scope, receive, send)
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if version != "2026-07-28":
            return await error(
                -32022, "Unsupported protocol version", 400,
                {"supported": ["2026-07-28"], "requested": version},
            )(scope, receive, send)
        if headers.get("mcp-protocol-version") != version or headers.get("mcp-method") != "server/discover":
            return await error(-32020, "Header mismatch", 400)(scope, receive, send)

        settings = payment_settings()
        price_text = (
            "A successful diagnosis costs exactly $0.01 USDC per call."
            if settings else "The paid trial is currently disabled; diagnosis calls are no-charge."
        )
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "resultType": "complete",
                "supportedVersions": ["2025-11-25", "2025-06-18", "2025-03-26"],
                "capabilities": {"tools": {}},
                "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "agentrescue", "version": "0.2.0"}},
                "instructions": f"Use tools/list, then call diagnose_failure with a sanitized HTTP, API, or MCP error. {price_text} Advice is read-only.",
                "ttlMs": 300000,
                "cacheScope": "public",
            },
        }
        return await JSONResponse(response)(scope, receive, send)


mcp = FastMCP(
    "AgentRescue",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "agentrescue-mcp.onrender.com",
            "agentrescue-mcp.onrender.com:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ],
        allowed_origins=[
            "https://agentrescue-mcp.onrender.com",
            "http://localhost",
            "http://127.0.0.1",
        ],
    ),
)


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
            from x402.schemas import ResourceInfo

            resource_server = x402ResourceServer(
                HTTPFacilitatorClient(FacilitatorConfig(url=settings["facilitator_url"]))
            )
            resource_server.register(settings["network"], ExactEvmServerScheme())
            resource_server.initialize()
            accepts = resource_server.build_payment_requirements(
                payment_resource_config(settings)
            )
            paid = create_payment_wrapper(
                resource_server,
                accepts=accepts,
                resource=ResourceInfo(
                    url="mcp://tool/diagnose_failure",
                    description="Bounded HTTP, API, and MCP error diagnosis",
                    mime_type="application/json",
                ),
                extensions=payment_discovery_extension(),
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
        f"HTTP API: POST {PUBLIC_BASE_URL}/v1/diagnose with a JSON error and optional system (http, api, or mcp).\n"
        f"MCP endpoint: {PUBLIC_BASE_URL}/mcp (Streamable HTTP). Discover tools freely with tools/list.\n"
        f"OpenAPI: {PUBLIC_BASE_URL}/openapi.json.\n"
        "Call diagnose_failure with a sanitized HTTP, API, or MCP error. Advice is read-only.\n"
        f"{price}\n"
        "Requests are limited to 60 GET and 20 POST per minute per instance; request and response bodies are capped at 16 KB.\n"
        "Do not send secrets or personal data.\n"
    )
    return PlainTextResponse(content)


async def openapi(request: Request):
    schema = copy.deepcopy(SCHEMA)
    schema["servers"] = [{"url": PUBLIC_BASE_URL}]
    schema["info"]["description"] = (
        "Rule-based, advisory HTTP/API/MCP failure diagnosis. Fixes are never executed. "
        "When x402 is enabled, POST /v1/diagnose requires $0.01 USDC."
    )
    diagnosis = schema["components"]["schemas"]["Diagnosis"]
    diagnosis["properties"]["payment"] = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["disabled", "x402-testnet", "x402-mainnet"]},
            "price_usd": {"type": "string", "enum": ["0.00", "0.01"]},
        },
        "required": ["mode", "price_usd"],
    }
    diagnose_post = schema["paths"]["/v1/diagnose"]["post"]
    if payment_settings():
        diagnose_post["responses"]["402"] = {
            "description": "x402 payment required; includes the accepted payment requirements."
        }
    return JSONResponse(schema)


async def diagnose_http(request: Request):
    """Validate a bounded HTTP request and return the shared safe diagnosis."""
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "json_object_required"}, status_code=400)
    if set(payload) - {"error", "system"}:
        return JSONResponse({"error": "unsupported_field"}, status_code=400)
    error = payload.get("error")
    if not isinstance(error, str) or not error.strip():
        return JSONResponse({"error": "error_required"}, status_code=400)
    if len(error) > MAX_DIAGNOSIS_CHARS:
        return JSONResponse({"error": "diagnostic_too_large", "max_chars": MAX_DIAGNOSIS_CHARS}, status_code=413)
    system = payload.get("system", "http")
    if not isinstance(system, str) or system not in {"http", "api", "mcp"}:
        return JSONResponse({"error": "invalid_system", "allowed": ["api", "http", "mcp"]}, status_code=400)

    settings = payment_settings()
    result = diagnose(error, system)
    result["payment"] = {
        "mode": "x402-" + settings["mode"] if settings else "disabled",
        "price_usd": "0.01" if settings else "0.00",
    }
    return JSONResponse(result)


async def feedback(request: Request):
    """Accept opted-in, category-only feedback when collection is explicitly enabled."""
    if os.environ.get("AGENTRESCUE_FEEDBACK_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "json_object_required"}, status_code=400)
    if payload.get("opt_in") is not True:
        return JSONResponse({"error": "explicit_opt_in_required"}, status_code=400)
    if set(payload) - {"opt_in", "category", "outcome"}:
        return JSONResponse({"error": "unsupported_feedback_field"}, status_code=400)

    category = payload.get("category", "unknown")
    outcome = payload.get("outcome", "unsure")
    if not isinstance(category, str) or category not in FEEDBACK_CATEGORIES:
        return JSONResponse({"error": "invalid_feedback_category"}, status_code=400)
    if not isinstance(outcome, str) or outcome not in FEEDBACK_OUTCOMES:
        return JSONResponse({"error": "invalid_feedback_outcome"}, status_code=400)

    # Store only minimized labels; never persist diagnostic text, identity, or request metadata.
    path = os.environ.get("AGENTRESCUE_FEEDBACK_PATH", "data/feedback.jsonl")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"category": category, "outcome": outcome, "at": int(time.time())}) + "\\n")
    return JSONResponse({"accepted": True, "stored": ["category", "outcome", "timestamp"]}, status_code=201)


async def home(request: Request):
    mode = payment_settings()
    status = "Payment trial is active: each successful diagnosis costs $0.01 USDC." if mode else "The payment trial is not enabled; no diagnosis charges are collected."
    html = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>AgentRescue</title><main><h1>Safer next steps for failing agents.</h1>"
        "<p>AgentRescue returns bounded, structured recovery guidance for HTTP, API, and MCP failures."
        " It never executes fixes.</p><p>" + status + "</p>"
        f"<p>Agents: POST a sanitized JSON error to <code>{PUBLIC_BASE_URL}/v1/diagnose</code> or connect to <code>{PUBLIC_BASE_URL}/mcp</code>. <a href='/llms.txt'>Agent guide</a> · <a href='/openapi.json'>OpenAPI</a>. Discovery and tool listing are free.</p>"
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
        Route("/openapi.json", openapi, methods=["GET"]),
        Route("/", home, methods=["GET"]),
        Route("/v1/diagnose", diagnose_http, methods=["POST"]),
        Route("/v1/feedback", feedback, methods=["POST"]),
        McpPostRoute(mcp_app),
        Mount("/", app=mcp_app),
    ],
    middleware=[Middleware(McpTrafficBounds)],
    lifespan=lifespan,
)

_http_payment_settings = payment_settings()
if _http_payment_settings:
    # The SDK protects only HTTP diagnosis calls; health, MCP discovery, and tool listing stay free.
    _http_middleware = http_payment_middleware(_http_payment_settings)
    app.add_middleware(_http_middleware.cls, **_http_middleware.kwargs)
