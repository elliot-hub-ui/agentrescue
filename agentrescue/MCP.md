# AgentRescue MCP service

AgentRescue is a public MCP diagnostic service for agents that encounter HTTP, API, or MCP failures. Connect to `https://agentrescue-mcp.onrender.com/mcp` using Streamable HTTP and call `diagnose_failure` with a sanitized error and optional system (`http`, `api`, or `mcp`). It returns structured evidence and advisory recovery guidance; it never executes fixes.

## Discovery and trial

MCP clients can use `server/discover`, `tools/list`, and `tools/call`. HTTP diagnostics are also available at `POST /v1/diagnose`; `GET /llms.txt` and `/openapi.json` describe the service and contract. Discovery and diagnosis are currently free. Production billing is not enabled.

## Traffic and response boundaries

- Each instance allows up to 60 GET and 20 POST requests per minute across all callers. Limits reset on process restart and are for a low-volume pilot, not DDoS protection.
- Request and response bodies are capped at 16 KB; a diagnostic is limited to 8,000 characters.
- Inputs are processed in memory. Request bodies are not logged or stored. Secret redaction is best-effort; send only synthetic or sanitized text.
- Recovery advice is informational. High-risk steps require human approval.

## Hosting and costs

The live service uses one 0.5 CPU / 512 MB Render web instance at approximately $7/month. Render Hobby workspaces include 5 GB of outbound bandwidth shared across services, then bill $0.15 per additional GB. The response cap and request limits bound the pilot, but Render does not impose a hard total spend cap. Check workspace usage and suspend the service before total spend approaches the approved $40 monthly ceiling.
