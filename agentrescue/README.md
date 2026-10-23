# AgentRescue

AgentRescue is an agent-callable HTTP/API/MCP failure diagnosis tool. Agents can call `diagnose_failure` for structured, evidence-linked recovery guidance. It never executes fixes.

## Run locally

Requires Python 3.12+. Start the free prototype with `python3 app.py`, then visit `http://127.0.0.1:8000`. The server binds to loopback by default and respects `HOST` and `PORT` for a hosted runtime.

- MCP: `POST /mcp` (stateless `2026-07-28` plus legacy initialize compatibility)
- HTTP diagnosis: `POST /v1/diagnose`
- OpenAPI: `/openapi.json`
- Agent discovery guide: `/llms.txt`
- Health: `/health`

The live Render service runs `paid_trial_app.py` on a single 0.5 CPU / 512 MB instance. HTTP and MCP diagnosis currently cost nothing because x402 is disabled; feedback collection is also off. The service has no account system, durable feedback store, production billing, or production support guarantee. Send sanitized excerpts only. Pattern-based redaction can miss credentials.

## Verify

Run the test suite with `python3 -m unittest`. To run all test and x402 adapter checks, install pinned dependencies: `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, then `.venv/bin/pip install -r requirements.lock`. The main prototype itself uses only the Python standard library.

## Paid-trial controls

`paid_trial_app.py` is the live HTTP and MCP entry point. It handles current MCP discovery, legacy clients, an HTTP Bazaar-discoverable `POST /v1/diagnose` route, AgentRescue guide resources, and the public discovery pages. The x402 payment code is disabled by default, so no diagnosis charge is collected. When enabled, the fixed price is $0.01 USDC per successful diagnosis through either HTTP or MCP. Test mode accepts Base Sepolia only; production mode accepts Base mainnet only. Both require an explicit non-zero receiving address, and invalid or incomplete settings stop service startup. The facilitator is fixed to `https://x402.org/facilitator` for test mode.

The production payment switch remains off until the owner supplies the receiving address, selects an HTTPS facilitator for mainnet, explicitly approves the production mode, and reviews the final live configuration. Test mode defaults to the public x402.org facilitator; the mainnet path rejects it and requires `AGENTRESCUE_X402_FACILITATOR`. Never put a private key or facilitator credential in Render or this repository. The service creates or controls no wallet and has not launched production payment collection.

The included `x402_mcp_test_once.py` is an isolated one-attempt test client. Do not clear its sentinel or repeat a testnet payment without separate explicit authorization.

The live MCP Registry listing is [AgentRescue 0.2.0](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.elliot-hub-ui%2Fagentrescue/versions/latest); the unapproved local candidate is version 0.2.1. Its rules pass 32 synthetic benchmark cases, which is not real-world validation. Confidence remains qualitative and uncalibrated. Render's recent request counts include launch checks and other probes, so they do not verify independent customer use. This is a pilot, not a validated or profitable product.
