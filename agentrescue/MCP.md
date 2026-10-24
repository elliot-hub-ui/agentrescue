# MCP connection

AgentRescue is an agent-callable diagnostic service. An agent may use `diagnose_failure` after an HTTP, API, or MCP call fails and the existing evidence does not resolve the issue. The tool returns a diagnosis, evidence signals, confidence basis, and recovery safety fields. It does not execute remediation.

## Local connection

Start the free prototype with `python3 app.py`. It binds to `127.0.0.1:8000` and exposes `POST http://127.0.0.1:8000/mcp`. Configure the agent's MCP client for Streamable HTTP at that URL. The modern path supports MCP `2026-07-28` stateless HTTP (`server/discover`, `tools/list`, and `tools/call`) and legacy initialize compatibility through `2025-11-25`.

When called directly by an agent, send only the smallest relevant error excerpt after removing credentials, personal data, and customer content. Inputs are capped at 8,000 characters; pattern-based redaction is not a guarantee. Treat the response as advisory evidence. Do not broaden permissions, disable TLS checks, retry non-idempotent requests, or take high-risk action without required human approval. Continue only after verifying the action is safe and the expected result is achieved.

## Discovery and payment

Discovery and tool listing are free. The hosted x402 implementation supports a fixed $0.01 USDC payment per successful diagnosis. It remains disabled until the owner provides a receiving address, selects an HTTPS production facilitator, explicitly approves mainnet, and reviews the final production configuration. Base mainnet rejects the public x402.org facilitator; testnet alone uses it by default. The build does not create or control a wallet, and no production payment is enabled by default.

When payment mode is enabled, the payment-required response includes Bazaar metadata for the `diagnose_failure` MCP tool, its input schema, and a synthetic example. A facilitator that implements Bazaar may catalog the tool if a client echoes the extension in a payment payload; indexing is facilitator-controlled and not guaranteed. This is a payment-driven discovery path separate from the MCP Registry; neither route guarantees that a client indexes or calls the tool, and ordinary MCP clients remain unable to pay unless they support x402.

Each process allows at most 60 GET and 20 POST requests per rolling minute, with 16 KB request and response caps. The low-volume limits reset on restart and are not DDoS protection. Feedback writes remain disabled. Send only synthetic or sanitized input; redaction is best-effort.

The app emits one runtime-log event for each MCP `diagnose_failure` invocation. It records only response status and payment mode so usage can be separated from initialization, listing, and health probes. It does not record the request body, error text, request ID, IP address, or user-agent. The count is not a unique-agent or confirmed-payment metric; Render's platform request logs may retain client metadata separately.

Render's estimated marginal bandwidth charge for the largest tested diagnostic response is a small fraction of one cent, so the proposed price has several-thousand-fold coverage of that marginal traffic cost. This is gross contribution before fixed hosting, facilitator/payment fees, refunds, taxes, and support; it does not establish profitability. Render does not impose a hard total spend cap, so monitor workspace usage against the approved $40 monthly ceiling.
