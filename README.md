# AgentRescue

AgentRescue helps AI agents diagnose HTTP, API, and MCP failures. It returns bounded, structured recovery guidance and never executes fixes.

## Live service

- **MCP:** `https://agentrescue-mcp.onrender.com/mcp` (Streamable HTTP)
- **HTTP diagnosis:** `POST https://agentrescue-mcp.onrender.com/v1/diagnose`
- **Developer setup:** `https://agentrescue-mcp.onrender.com/developers`
- **Pricing and current payment status:** `https://agentrescue-mcp.onrender.com/pricing`
- **OpenAPI:** `https://agentrescue-mcp.onrender.com/openapi.json`
- **Agent instructions:** `https://agentrescue-mcp.onrender.com/llms.txt`

The live service runs `agentrescue/paid_trial_app.py`. Diagnosis is currently free because x402 payments are disabled. The public registry listing is [AgentRescue 0.2.0](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.elliot-hub-ui%2Fagentrescue/versions/latest). No customer demand or production revenue has been verified.

Send only synthetic or sanitized error excerpts; secret redaction is best-effort. Recovery guidance is advisory, confidence is qualitative and uncalibrated, and high-risk steps require human review.

## Run locally

Requires Python 3.12+. Install the pinned dependencies from `agentrescue/requirements.txt` and `agentrescue/requirements.lock`, then start the hosted entry point from `agentrescue/` with `python -m uvicorn paid_trial_app:app --host 127.0.0.1 --port 8000`. For the minimal standard-library prototype, run `python3 app.py` from `agentrescue/`.

Run checks from `agentrescue/` with `.venv/bin/python -m compileall -q .` and `.venv/bin/python -m unittest -q`.

## Payments

The proposed price is $0.01 USDC per successful diagnosis when the service owner explicitly enables x402. Production payments are disabled. Never put wallet private keys or facilitator credentials in Render or this repository. Production activation requires an owner-provided receiving address, a selected HTTPS facilitator, and explicit review and approval of the live configuration.

See [technical setup](agentrescue/README.md), [unit economics](venture/economics.md), [acceptance status](venture/acceptance.md), and the [synthetic benchmark](venture/benchmark.json).
