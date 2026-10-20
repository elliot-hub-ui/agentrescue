# AgentRescue

An MCP service for agents that need a safe next step when an HTTP, API, or MCP call fails.

AgentRescue analyzes a sanitized error and returns a structured diagnosis, evidence, qualitative confidence, and recovery guidance. It does not execute repairs, retry requests, connect to customer systems, or collect payment.

## Try the hosted MCP service

Connect an MCP client to `https://agentrescue-mcp.onrender.com/mcp`. The server supports the `diagnose_failure` tool. It accepts an error message and an optional system category (`http`, `api`, or `mcp`). See [`agentrescue/MCP.md`](agentrescue/MCP.md) for protocol details.

Only send synthetic or sanitized examples. Secret redaction is best-effort. The service processes requests in memory, does not log request bodies, and does not save feedback. A coarse per-instance request limit protects the low-volume pilot.

## Run locally

Python 3.10+ is recommended; runtime code uses only the standard library.

```sh
cd agentrescue
HOST=127.0.0.1 PORT=8000 python3 app.py
python3 -m unittest test_app test_benchmark test_handlers -v
```

## Deploy

The repository-level [`render.yaml`](render.yaml) provisions a single always-on 0.5 CPU / 512 MB Render service with manual deployments and no database. Its compute price is approximately $7/month. Render Hobby workspaces include 5 GB of monthly outbound bandwidth and charge $0.15 per additional GB; the available spend cap applies to build-pipeline minutes, not total service spend. Monitor bandwidth and billing, and suspend the pilot before the approved $40 ceiling.

## Project status

This is an early validation pilot. The included benchmark is synthetic and is not evidence of customer demand or product accuracy. No customer outcomes have been collected. Success means agents independently discover the service, repeatedly use its diagnostics, and provide evidence that the saved recovery time is worth paying for.
