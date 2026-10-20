# MCP connection

AgentRescue is an agent-callable diagnostic service. An agent may use `diagnose_failure` after an HTTP, API, or MCP call fails and the existing evidence does not resolve the issue. The tool returns a diagnosis, evidence signals, confidence basis, and recovery safety fields. It does not execute remediation.

## Local connection

Start the free prototype with `python3 app.py`. It binds to `127.0.0.1:8000` and exposes `POST http://127.0.0.1:8000/mcp`. Configure the agent's MCP client for Streamable HTTP at that URL. The modern path supports MCP `2026-07-28` stateless HTTP (`server/discover`, `tools/list`, and `tools/call`) and legacy initialize compatibility through `2025-11-25`.

When called directly by an agent, send only the smallest relevant error excerpt after removing credentials, personal data, and customer content. Inputs are capped at 8,000 characters; pattern-based redaction is not a guarantee. Treat the response as advisory evidence. Do not broaden permissions, disable TLS checks, retry non-idempotent requests, or take high-risk action without required human approval. Continue only after verifying the action is safe and the expected result is achieved.

## Discovery and payment

The service exposes MCP `server/discover`, `tools/list`, and `tools/call`. The public pilot is free and no-charge, with a shared cap of 20 POST requests per minute per process. Feedback writes are disabled unless `AGENTRESCUE_FEEDBACK_ENABLED=true` is explicitly configured; do not enable that on the public demo. The x402 server is an isolated Base Sepolia test only, not production billing. Public deployment is approved and being configured at `https://agentrescue-mcp.onrender.com/mcp`; a separate MCP Registry listing has not been authorized. Render Free sleeps after idle periods, so this endpoint is for low-volume trials, not production reliability.
