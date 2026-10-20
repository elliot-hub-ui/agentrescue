# AgentRescue public MCP service

AgentRescue gives LLM agents structured, advisory diagnosis for common HTTP, API and MCP failures. It never runs fixes. Confidence is qualitative, not a calibrated probability. Send only synthetic or sanitized diagnostic examples; secret redaction is best-effort.

## Connect

- Public trial MCP: `https://<deployed-host>/mcp`
- Website and service overview: `/` and `/llms.txt`
- MCP capability discovery: `server/discover`, then `tools/list`
- Tool: `diagnose_failure`; arguments: `error` (required) and `system` (`http`, `api`, or `mcp`)
- HTTP API: `POST /v1/diagnose`
- OpenAPI: `/openapi.json`
- Health: `/health`

The public trial is free. Payments are not enabled. The deployed server has no wallet integration, no API keys, no customer accounts, no feedback endpoint, and no persistent database. It processes inputs in memory and does not log request bodies. A coarse global limit caps POST traffic at 20 requests/minute per instance. Request body limit is 16 KB and diagnostic text limit is 8,000 characters. The rate counter resets on process restart and is intended for low-volume evaluation, not as DDoS protection.

## Local run

Python 3.10+ recommended; runtime uses only the standard library.

```sh
HOST=127.0.0.1 PORT=8000 python3 app.py
python3 -m unittest test_app test_benchmark test_handlers -v
```

## Deployment

`../render.yaml` configures one Render 0.5 CPU / 512 MB web service, no database, health checks and manual deploys. Current estimated compute is about $7/month. Render's Hobby workspace includes 5 GB of outbound bandwidth, then charges $0.15/GB; its spend limit only covers build-pipeline minutes. Watch the workspace Billing page and service bandwidth metrics, and suspend the service if the pilot approaches the approved $40 ceiling. Deploy only this `app.py` service. No automated deploys are configured.

Render Free is unsuitable for unattended agent discovery: free web services sleep after 15 minutes and may serve a default robots-deny response while asleep. See [Render free service limits](https://render.com/docs/free).

## Data and limitations

Diagnostics are evaluated in memory. HTTP server access logging is disabled and request bodies are never written to disk. Render/platform edge logs may still record request metadata such as IP address and path; do not send private diagnostic content. The service has no persistence or outcome learning. Synthetic benchmark scores are not customer evidence. Render does not provide a hard cap for total service compute and bandwidth; monitor billing and suspend the service before total spend reaches the approved $40 ceiling.
