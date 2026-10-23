# AgentRescue economics and revenue architecture

Updated 2026-10-19. The scenarios below are explicit arithmetic placeholders, not forecasts or customer evidence. Price, churn, CAC, costs, and demand are all unverified.

## Bandwidth margin guard (2026-10-20)

Render currently includes 5 GB of outbound traffic across the Hobby workspace, then charges $0.15/GB. Source: [Render outbound bandwidth documentation](https://render.com/docs/outbound-bandwidth), checked 2026-10-20. Bandwidth is shared with other services in that workspace, so use the full marginal rate for conservative per-call math even while this service remains below the allowance.

Measured serialized response bodies from the release code (local handler tests; transport/TLS headers excluded): 468 bytes for a normal HTTP diagnosis, 931 bytes for an 8,000-character HTTP diagnostic, and 2,070 bytes for an 8,000-character MCP diagnosis. The new 16,000-byte hard response cap bounds any larger response. At $0.15/decimal GB, a full-cap response costs at most $0.0000024 of marginal bandwidth; at a proposed $0.01 paid diagnosis, gross revenue is at least 4,166× the maximum response-bandwidth charge. At the largest tested MCP response, the ratio is about 32,206×. These ratios exclude payment processing, compute, support, CAC, and maintenance; they are not total gross margin.

For scale, 10,000 paid calls at $0.01 would produce $100 gross revenue and about 20.7 MB of largest-tested responses, costing roughly $0.0031 at the marginal bandwidth rate. One million such calls would be $10,000 gross and about 2.07 GB / $0.31 in response bandwidth. All call revenue figures are hypothetical: the public service is currently no-charge, the production payment path is disabled, and no buyer has validated this price. The separate $0.01 Base Sepolia transaction is test currency only.

Guardrails now bound each instance to 60 GET/minute and 20 POST/minute and cap response bodies at 16 KB. At the deliberately pessimistic assumption that every allowed request returns a full 16 KB, one month (30 days) would send about 55.3 GB from this service, or approximately $7.54 above the 5 GB workspace allowance if no other services used it. This leaves room under the previously authorized $40 monthly pilot ceiling, but the bandwidth allowance is shared and Render has no hard total-spend cap; inspect actual workspace billing and suspend before the ceiling. This rate limit is a low-volume pilot bound, not DDoS protection.

**Paid-trial build approved; production launch still gated:** keep `server/discover`, `tools/list`, health, and docs free; charge exactly $0.01 per successful diagnosis through x402; do not offer unlimited paid plans; enforce a hard output limit and expose the exact price before the paid call. The public implementation is disabled by default until the owner supplies a receiving address and reviews the final production configuration. Do not claim revenue exceeds bandwidth until real paid transactions and provider bandwidth are observed. At the trial price, validate buyer willingness to pay and payment costs before scaling.

**Bandwidth conclusion, with limits stated:** at the hard 16 KB response cap, public egress is at most $0.0000024 per response at the documented marginal rate of $0.15/GB, versus $0.01 gross per paid diagnosis (about 4,166:1). If the 20 POST/minute cap were saturated for 30 days and every POST produced a maximum-size response, total outbound traffic across all endpoints would be about 55.3 GB; even charging every byte at the public rate with no included allowance, that is about $8.30. This is a stress ceiling, not observed usage, and includes free requests. A $7/month compute charge alone takes 700 successful $0.01 calls to cover before fees, acquisition, support, taxes, and maintenance. Render reported 0.008732796 MB in the 2026-10-20 16:00 UTC sample; this is a single interval, not month-to-date or billing evidence. Production revenue remains $0. The economic risk to test next is payment/facilitator cost and actual paid conversion, not per-call bandwidth.

## Scenario model (monthly USD)

### Current $0.01 per-diagnosis trial model

The paid-trial build is priced per successful diagnosis, so this call-based model is the current decision model. All demand, acquisition, payment-fee, support, and retention inputs remain speculative. Render compute is $7/month. Egress is conservatively charged at the full 16 KB response cap and $0.15/GB; the service currently makes no paid calls.

| Case | Active paying operators; calls/operator; new/mo, churn | Calls / revenue | Hosting | API/data + egress | Payment fees | Support labor | CAC | Maintenance | Compliance | Contribution | Break-even |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pessimistic | 1; 500; 1 new, 100% churn | 500 / $5 | $7 | $0.0012 | $5 (100% fee stress) | $20 | $100 | $240 | $10 | **−$377.00** | Undefined: modeled payer contribution is negative |
| Base | 10; 1,000; 1 new, 10% churn | 10,000 / $100 | $7 | $0.024 | $3 (3% fee assumption) | $25 | $60 | $120 | $10 | **−$125.02** | ~115 active operators under base retention/cost assumptions |
| Optimistic | 100; 1,000; 5 new, 5% churn | 100,000 / $1,000 | $7 | $0.24 | $30 (3% fee assumption) | $50 | $300 | $60 | $10 | **$542.76** | ~13 active operators under optimistic retention/cost assumptions |

Fee percentages are placeholders, not x402 facilitator quotes. A flat fee per settled transaction could consume a large share of a one-cent price; the actual production fee and settlement behavior must be measured. Base-case variable contribution is about $1.20/operator/month after 10% churn replacement cost ($60 CAC × 10%) and $2.50 support per operator; fixed operating cost is $137/month, so break-even is approximately 115 active operators. CAC ×3 lowers base contribution to **−$245.02**; API/data+egress ×5 lowers it to **−$125.12**; both stresses produce **−$245.12**. This shows that fixed operation, acquisition, and retention dominate bandwidth. It is not profit evidence.

At the call level, a 3% payment-fee assumption plus worst-case response egress leaves about $0.0096976 per call before support, acquisition, maintenance, and compliance. The $7 compute-only floor is 700 paid calls/month; the base model requires about 40 active operators at 1,000 calls each because of fixed and acquisition/support costs. At the current 20 POST/minute cap, the theoretical maximum is 864,000 POSTs/month, but many requests are free protocol setup/list calls, so this is not a revenue forecast.

### Alternative $29 subscription scenario (not the current trial price)

Contribution = revenue − hosting − API/data − payment fees − support labor − CAC − maintenance − compliance. The following older subscription scenarios are retained only as an unvalidated alternative; they are not the approved trial price.

| Case | Customers, ARPU; new/mo, churn | Revenue | Hosting | API/data | Fees | Support | CAC | Maintenance | Compliance | Contribution | Break-even |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pessimistic | 5 at $10; 1 new/mo, 20% churn | $50 | $30 | $25 | $1.50 | $25 | $100 | $240 | $10 | **−$381.50** | Undefined; recurring acquisition cost makes per-customer contribution negative |
| Base | 50 at $29; 2.5 new/mo, 5% churn | $1,450 | $30 | $50 | $43.50 | $125 | $150 | $240 | $50 | **$761.50** | ~15 customers |
| Optimistic | 200 at $49; 6 new/mo, 3% churn | $9,800 | $200 | $200 | $294 | $500 | $360 | $300 | $100 | **$7,846** | ~15 customers |

Base assumptions: 3% payment cost; 5 support minutes/customer/month valued at $30/hour; 5% monthly churn replaced by 2.5 new customers/month at $60 CAC; $1/customer API/data; $240 maintenance and $50 compliance reserve. Pessimistic assumes $10 ARPU, 20% monthly churn replaced at $100 CAC, $5/customer API/data, and 10 support minutes/customer/month. Optimistic assumes $49 ARPU, 3% monthly churn replaced at $60 CAC, and stronger scale. No provider quote or buyer evidence supports any of these inputs.

Stress tests against base: CAC ×3 raises monthly CAC from $150 to $450 and lowers contribution to **$461.50**. API/data ×5 raises that line from $50 to $250 and lowers contribution to **$561.50**. Combined stress leaves **$161.50** in this hypothetical. These numbers remain speculative; use actual costs and conversion before investment.

### Break-even sensitivity

Under base assumptions, variable contribution per active account is `$29 × 97% − $1 API/data − $2.50 support − (5% churn × $60 CAC) = $21.63`. Fixed monthly cost is $320 (hosting, maintenance, compliance). At 15, 50, and 100 active accounts, the corresponding minimum subscription price for break-even is approximately **$28.69, $13.30, and $10.00/month**. At 5 and 10 accounts, it rises to **$72.68 and $39.69/month**.

At a $29/month price and base variable costs, modeled break-even is 15 accounts at 5% monthly churn, 18 at 10%, 26 at 20%, 49 at 30%, and 508 at 40%. Per-account contribution becomes negative above roughly 41% monthly churn, so no customer count can cover fixed cost under those assumptions. This sensitivity shows that retention and customer acquisition dominate the plan; it is arithmetic only, not observed retention, willingness to pay, or a forecast.

Time to first revenue and time to positive cash flow are **unknown**. No customers or production collection exist. The ~15-customer base break-even uses $320 fixed monthly costs divided by roughly $21.63 contribution per account after variable service, fee, and 5%-churn replacement CAC ($60 × 5%). The optimistic break-even is also about 15 customers under its 3%-churn assumption. The pessimistic case has negative per-customer contribution after recurring acquisition cost, so break-even is undefined. Churn, CAC, and all other inputs remain speculative; these calculations are scenarios, not forecasts.

## Revenue path and autonomy

Buyer/payer: an agent operator with explicit delegated spend authority; agents are the intended direct users. The $0.01-per-diagnosis price is approved for the build but remains unvalidated with buyers; a $29/month subscription is only an alternative hypothesis. The current public pilot is no-charge and stateless, with coarse global per-instance traffic limits. Proposed paid boundary: diagnosis requires a metered, agent-compatible payment; MCP discovery, tool listing, health, and docs remain free. The isolated Base Sepolia x402 transaction proves protocol plumbing only; production payments, billing reconciliation, entitlements, upgrades, and cancellation are not enabled. Acquisition hypotheses are docs and agent/MCP registries; CAC is unknown. Activation is a discovered and completed diagnosis with owner-approved spend. Retention must come from observed repeat use and measurable task benefit.

Illustrative labor model: 6.7 minutes/account/month plus 240 fixed maintenance minutes. This yields approximately 5.1, 15.2, and 115.7 human hours/month at 10, 100, and 1,000 customers. At $29/month, that is approximately 1,059, 314, and 239 human minutes per $1,000 revenue. Target is at most 300 minutes per $1,000 after operations are measured; remediate or stop scaling if labor remains above that at 100 customers. These estimates are not observed.

## Render plan and observed usage — 2026-10-22

Render's service list shows six services in the shared workspace, including AgentRescue on a paid 0.5 CPU / 512 MB instance. Render metrics for 2026-10-01 through 2026-10-22 22:54 UTC total approximately **84.5 MB** outbound bandwidth across those six services; AgentRescue accounts for **0.40 MB**. This is about 1.7% of Hobby's 5 GB included bandwidth, though it excludes any usage outside the listed services or later in the billing period.

The user-provided plan screenshot shows Pro. Render's current official pricing lists Pro at **$25/month** with 25 GB and Hobby at **$0/month** with 5 GB; overage is **$0.15/GB**. The existing AgentRescue Starter compute is separately estimated at **$7/month** and would remain paid if the workspace moved to Hobby. Thus, a Hobby workspace could lower the shared baseline by up to $25/month while leaving AgentRescue compute always-on; gross hosting break-even at $0.01 would fall from about 3,200 calls on the $32 Pro-plus-compute allocation to about 700 calls on $7 compute. These are fixed-cost calculations only, not net profit or demand forecasts.

This is a **recommendation to review**, not a plan change. Render's tools did not expose the invoice, other workspace usage outside the six listed services, or member count. Pro-only features include multiple members, compliance reports, audit logs, autoscaling and isolated environments; the six listed services use no paid AgentRescue autoscaling and the service has no custom domain, but workspace-wide needs are unknown. A downgrade would affect every service in the workspace. Do not change the workspace plan until the owner confirms those needs and approves it. Sources: [Render pricing](https://render.com/pricing), [workspace plan comparison](https://render.com/docs/new-workspace-plans), [outbound bandwidth](https://render.com/docs/outbound-bandwidth), and [compute plans](https://render.com/docs/compute-plans).

## Registry launch, observed demand, and price sensitivity — 2026-10-23

The live service now runs the tested HTTP/MCP app with payments and feedback off. The official MCP Registry reports `io.github.elliot-hub-ui/agentrescue` version `0.2.0` as active: [public listing](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.elliot-hub-ui%2Fagentrescue/versions/latest). This improves discoverability but does not establish usage or willingness to pay.

Render's 2026-10-16 18:15 UTC to 2026-10-23 18:15 UTC metrics show **7** requests to `/v1/diagnose` and **31** to `/mcp`. Our own launch checks, earlier QA, and scans are included in these counts; the service does not identify the remaining callers, so none of these requests is counted as verified independent customer demand. No paid request or production settlement is observed; x402 remains disabled.

The following are gross hosting-only break-even counts, using roughly **$32/month** for the Pro workspace plus AgentRescue compute, or **$7/month** for AgentRescue compute alone. They assume every counted request is a successful paid diagnosis and exclude payment fees, acquisition, support, taxes, and maintenance. They are arithmetic, not a price recommendation or revenue forecast.

| Hypothetical price per paid diagnosis | Calls to cover ~$32/month | Calls to cover ~$7/month |
|---:|---:|---:|
| $0.01 | 3,200 | 700 |
| $0.05 | 640 | 140 |
| $0.10 | 320 | 70 |
| $0.25 | 128 | 28 |
| $1.00 | 32 | 7 |

The x402 project documentation describes facilitators as verifying and settling payments, and says Coinbase's facilitator adds no fee on Base; that does not prove the current service has a production facilitator or that settlement is costless to AgentRescue. A supported, owner-approved production facilitator must be selected and actual costs measured before treating one cent as profitable. Source: [x402 facilitator and fee guidance](https://x402.gitbook.io/x402/core-concepts/facilitator).

Decision: keep the public pilot free while discovery and value are unverified. Before enabling charges, collect evidence that independent agents complete useful diagnoses and that an agent operator accepts a specific price. If usage is real but the one-cent price cannot cover fixed costs, test a higher price with users before changing the live offer; price sensitivity above is only a planning aid.
