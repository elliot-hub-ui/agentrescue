# AgentRescue

AgentRescue is an MCP-callable HTTP/API/MCP failure diagnosis tool for AI agents. Agents can call `diagnose_failure` for structured, evidence-linked recovery guidance. It never executes fixes.

## Connect

After deployment, add `https://agentrescue-mcp.onrender.com/mcp` as a Streamable HTTP MCP server. The tool is `diagnose_failure`; see [`agentrescue/MCP.md`](agentrescue/MCP.md) for the calling and safety contract.

Send only synthetic or sanitized excerpts. Secret redaction is best-effort. The public pilot is free and no-charge. Each instance caps traffic at 60 GET and 20 POST requests per minute; response bodies are capped at 16 KB. These coarse limits reset on restart and are not account-level abuse protection. Feedback writes are disabled by default. The app does not persist credentials, request bodies, or feedback. Render may retain request metadata in platform logs.

## Local run and tests

Python 3.12+:

```sh
cd agentrescue
HOST=127.0.0.1 PORT=8000 python3 app.py
python3 -m unittest -v
```

The main server uses only the Python standard library. The optional x402 testnet adapter tests require pinned dependencies in `agentrescue/requirements.txt` and `agentrescue/requirements.lock`. The isolated x402 test server is not part of the public service and has no mainnet mode.

## Hosting

`render.yaml` specifies one always-on 0.5 CPU / 512 MB Render service with no database. Its compute plan costs about $7/month. The Hobby workspace includes 5 GB of outbound bandwidth shared across services, then charges $0.15/GB. The service is a no-charge evaluation pilot; watch workspace billing and suspend before the approved $40 monthly ceiling. Render does not provide a hard total-spend cap.

## Product status

This is a pilot, not a validated or profitable product. The included benchmark is synthetic, and rule confidence is qualitative and uncalibrated. Real agent task lift, retention, and revenue remain unproven.
