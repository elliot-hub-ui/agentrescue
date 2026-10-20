# AgentRescue

AgentRescue is an MCP tool for AI agents diagnosing HTTP, API, and MCP failures. It returns bounded, read-only recovery guidance; it never executes fixes.

## Connect

MCP endpoint: `https://agentrescue-mcp.onrender.com/mcp` using Streamable HTTP.

For VS Code, [install AgentRescue](vscode:mcp/install?%7B%22name%22%3A%22agentrescue%22%2C%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fagentrescue-mcp.onrender.com%2Fmcp%22%7D). VS Code will ask you to review and trust the server. This install link is specific to VS Code.

Discovery and tool listing are free. The **live Render service currently runs the no-charge prototype**. The paid-trial implementation is published and passes CI, but is not yet live. Its Render blueprint selects `agentrescue/paid_trial_app.py` and keeps `AGENTRESCUE_X402_ENABLED=0`; the existing service has manual settings that still start `agentrescue/app.py`.

The proposed paid trial costs exactly **$0.01 USDC per successful diagnosis** through x402. Payments remain disabled until the owner supplies a receiving address, selects a production HTTPS facilitator, explicitly approves mainnet, and reviews the exact live configuration. No production revenue is currently collected.

Send only synthetic or sanitized error excerpts. Secret redaction is best-effort. Requests are limited to 60 GET and 20 POST per minute per instance, with 16 KB request and response caps. The service does not intentionally persist diagnostic requests.

## Bandwidth and unit economics

At a maximum 16 KB response, marginal public egress at Render's documented $0.15/GB rate is at most **$0.0000024 per response**. Against a $0.01 paid diagnosis, gross call revenue is about **4,166× the maximum response-bandwidth cost**. This excludes fixed compute, payment/facilitator fees, support, acquisition, taxes, and maintenance, so it does not prove profitability.

The live Render service uses one Starter instance (0.5 CPU / 512 MB) at about $7/month compute. The user-provided Render Pro plan is $25/month and includes 25 GB outbound bandwidth at the workspace level. The plan and bandwidth are shared across services, so the workspace fee is not an AgentRescue-only cost; the invoice and workspace-wide usage have not been verified. No hard spend cap is configured. A single Render metrics sample on 2026-10-20 was 0.0087 MB; it is not a monthly total. The current illustrative base case (10 operators making 1,000 calls/month) yields $100 gross and about −$125 contribution after assumed acquisition, support, maintenance, payment fees, and hosting; modeled break-even is about 115 active operators. These inputs are speculative and are not evidence of demand or profitability.

See [technical setup](agentrescue/README.md), [unit economics](venture/economics.md), [acceptance status](venture/acceptance.md), the [synthetic benchmark](venture/benchmark.json), and [GitHub Actions](https://github.com/elliot-hub-ui/agentrescue/actions) for details.
