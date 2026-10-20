# AgentRescue

AgentRescue is an agent-callable HTTP/API/MCP failure diagnosis tool. Agents can call `diagnose_failure` for structured, evidence-linked recovery guidance. It never executes fixes.

## Run locally

Requires Python 3.12+. Start the free prototype with `python3 app.py`, then visit `http://127.0.0.1:8000`. The server binds to loopback by default and respects `HOST` and `PORT` for a hosted runtime.

- MCP: `POST /mcp` (stateless `2026-07-28` plus legacy initialize compatibility)
- HTTP diagnosis: `POST /v1/diagnose`
- OpenAPI: `/openapi.json`
- Agent discovery guide: `/llms.txt`
- Health: `/health`

The hosted free demo is no-charge and applies a shared limit of 20 POST requests per minute per process. Feedback writes are disabled unless `AGENTRESCUE_FEEDBACK_ENABLED=true` is set; do not enable this on the public demo. The service has no account system, durable feedback store, production billing, or production support guarantee. Send sanitized excerpts only. Pattern-based redaction can miss credentials.

## Verify

Run the test suite with `python3 -m unittest`. To run all test and x402 adapter checks, install pinned dependencies: `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, then `.venv/bin/pip install -r requirements.lock`. The main prototype itself uses only the Python standard library.

## Experimental x402 testnet code

`x402_mcp_server.py` and `x402_mcp_test_once.py` are separate, opt-in Base Sepolia testnet experiments. They are not launched by the free service, have no mainnet mode, and do not constitute production billing. The test client uses a one-attempt sentinel. Do not clear it or make a testnet payment without separate explicit authorization. Never place private keys or credentials in this repository.

Confidence is qualitative and uncalibrated; the phrase rules have only been checked against a small, synthetic benchmark. This is a pilot, not a validated or profitable product.
