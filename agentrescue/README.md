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

## Paid-trial controls

`paid_trial_app.py` is the prepared paid-trial MCP entry point. It handles current MCP discovery and legacy clients. The live Render service still runs `app.py` until its manual service settings are changed; the Render Blueprint in the repository is prepared for `paid_trial_app.py` and keeps x402 disabled. The x402 payment code is disabled by default, so no diagnosis charge is collected until the owner explicitly enables it. The fixed price is $0.01 USDC per successful diagnosis. Test mode accepts Base Sepolia only; production mode accepts Base mainnet only. Both require an explicit non-zero receiving address, and invalid or incomplete settings stop service startup. The facilitator is fixed to `https://x402.org/facilitator`.

The production payment switch must remain off until the owner supplies the receiving address, selects an HTTPS facilitator for mainnet, explicitly approves the production mode, and reviews the final live configuration. Test mode defaults to the public x402.org facilitator; the mainnet path rejects it and requires `AGENTRESCUE_X402_FACILITATOR`. Never put a private key or facilitator credential in Render or this repository. This build creates or controls no wallet and has not launched production payment collection.

The included `x402_mcp_test_once.py` is an isolated one-attempt test client. Do not clear its sentinel or repeat a testnet payment without separate explicit authorization.

Confidence is qualitative and uncalibrated; the phrase rules have only been checked against a small, synthetic benchmark. This is a pilot, not a validated or profitable product.
