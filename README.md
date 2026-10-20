# AgentRescue

AgentRescue is an MCP-callable HTTP/API/MCP failure diagnosis tool for AI agents. Agents can call `diagnose_failure` for structured, evidence-linked recovery guidance. It never executes fixes.

## Connect

After deployment, add `https://agentrescue-mcp.onrender.com/mcp` as a Streamable HTTP MCP server. The tool is `diagnose_failure`; see [`agentrescue/MCP.md`](agentrescue/MCP.md) for the calling and safety contract.

Send only synthetic or sanitized excerpts. Secret redaction is best-effort. The public pilot is free and no-charge. It uses an in-memory limit of 20 POST requests per minute per process; the limit resets on restart and is not account-level abuse protection. Feedback writes are disabled by default. The app does not persist credentials, request bodies, or feedback. Render may retain request metadata in platform logs.

## Local run and tests

Python 3.12+:

```sh
cd agentrescue
HOST=127.0.0.1 PORT=8000 python3 app.py
python3 -m unittest -v
```

The main server uses only the Python standard library. The optional x402 testnet adapter tests require pinned dependencies in `agentrescue/requirements.txt` and `agentrescue/requirements.lock`. The isolated x402 test server is not part of the public service and has no mainnet mode.

## Hosting

`render.yaml` specifies one free Python web service with no database or paid resources. Free Render services can sleep when idle and take time to wake; this is a low-volume evaluation endpoint, not dependable production infrastructure. The service is stateless and no-charge. Do not upgrade its plan or add paid services without explicit approval.

## Product status

This is a pilot, not a validated or profitable product. The included benchmark is synthetic, and rule confidence is qualitative and uncalibrated. Real agent task lift, retention, and revenue remain unproven.
