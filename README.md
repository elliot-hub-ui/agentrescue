# AgentRescue

AgentRescue is an MCP tool for AI agents diagnosing HTTP, API, and MCP failures. It returns bounded, read-only recovery guidance; it never executes fixes.

## Connect

MCP endpoint: `https://agentrescue-mcp.onrender.com/mcp` using Streamable HTTP.

Discovery and tool listing are free. The **live Render service currently runs the no-charge prototype**. The paid-trial implementation is published and passes CI, but is not yet live. Its Render blueprint selects `agentrescue/paid_trial_app.py` and keeps `AGENTRESCUE_X402_ENABLED=0`; the existing service has manual settings that still start `agentrescue/app.py`.

The proposed paid trial costs exactly **$0.01 USDC per successful diagnosis** through x402. Payments remain disabled until the owner supplies a receiving address and reviews the live production configuration. No production revenue is currently collected.

Send only synthetic or sanitized error excerpts. Secret redaction is best-effort. Requests are limited to 60 GET and 20 POST per minute per instance, with 16 KB request and response caps. The service does not intentionally persist diagnostic requests.

## Bandwidth and unit economics

At a maximum 16 KB response, marginal public egress at Render's documented $0.15/GB rate is at most **$0.0000024 per response**. Against a $0.01 paid diagnosis, gross call revenue is about **4,166× the maximum response-bandwidth cost**. This excludes fixed compute, payment/facilitator fees, support, acquisition, taxes, and maintenance, so it does not prove profitability.

The Render service uses one 0.5 CPU / 512 MB instance at about $7/month compute. It therefore needs roughly **700 successful paid calls just to cover compute**, before other costs. The 5 GB Hobby bandwidth allowance is shared across workspace services; review actual workspace billing and keep total spend under the approved $40 ceiling. A single Render metrics sample on 2026-10-20 was 0.0087 MB; no production payments or customer use have been observed.

See `venture/economics.md` and `venture/acceptance.md` for assumptions, limits, and current validation status.
