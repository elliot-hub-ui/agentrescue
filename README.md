# AgentRescue

AgentRescue is an MCP-callable HTTP/API/MCP failure diagnosis tool for AI agents. Agents can call `diagnose_failure` for structured recovery guidance. It never executes fixes.

## Connect

Connect an MCP client to `https://agentrescue-mcp.onrender.com/mcp` using Streamable HTTP. Discovery and tool listing are free. The paid-trial implementation charges exactly $0.01 USDC per successful diagnosis through x402 when explicitly enabled; payment collection is disabled by default and requires an owner-supplied receiving address and final review.

Send only synthetic or sanitized excerpts. Secret redaction is best-effort. Traffic is capped at 60 GET and 20 POST requests per minute per instance, with 16 KB request/response limits. The app does not persist credentials or request bodies.

## Local development

Python 3.12+:

```sh
cd agentrescue
python3 app.py
python3 -m unittest -v
```

The hosted MCP entry point is `paid_trial_app.py`. Render deployment is defined in `render.yaml`; it pins dependencies, runs the test suite, uses the existing 0.5 CPU / 512 MB service plan, and leaves x402 payments disabled.

## Economics and product status

At $0.01 per diagnosis and the largest measured response, estimated marginal bandwidth is several thousand times lower than the call price. That is gross contribution before fixed hosting, facilitator/payment fees, refunds, taxes, and support. It does not prove profitability. Agent demand, task lift, and repeat use remain unvalidated; see `venture/` for the synthetic benchmark and pilot plan.
