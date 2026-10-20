"""Exercise x402 MCP success and settlement-failure behavior without a payment."""
import json
import unittest
from types import SimpleNamespace

try:
    from x402.mcp.server import create_payment_wrapper
    from x402.mcp.types import MCP_PAYMENT_META_KEY, MCP_PAYMENT_RESPONSE_META_KEY
    from x402.schemas import (
        PaymentPayload,
        PaymentRequired,
        PaymentRequirements,
        ResourceInfo,
        SettleResponse,
        VerifyResponse,
    )
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(
        f"Optional x402 wrapper dependencies are unavailable ({exc.name}); "
        "install requirements.txt and requirements.lock to run this test"
    ) from exc

from app import diagnose
from paid_trial_app import payment_discovery_extension


NETWORK = "eip155:84532"
PAY_TO = "0x1111111111111111111111111111111111111111"
ASSET = "0x2222222222222222222222222222222222222222"


class FakeResourceServer:
    """Return deterministic verification/settlement results; never contacts a facilitator."""

    def __init__(self, settlement_success):
        self.settlement_success = settlement_success
        self.payment_required_extensions = None
        self.accepts = [PaymentRequirements(
            scheme="exact",
            network=NETWORK,
            asset=ASSET,
            amount="10000",
            pay_to=PAY_TO,
            max_timeout_seconds=60,
            extra={"name": "USDC", "version": "2"},
        )]
        self.verify_calls = 0
        self.settle_calls = 0

    def create_payment_required_response(self, accepts, resource, _payload=None, extensions=None):
        self.payment_required_extensions = extensions
        return PaymentRequired(accepts=accepts, resource=resource, extensions=extensions)

    def find_matching_requirements(self, accepts, payload):
        return accepts[0]

    def verify_payment(self, payload, requirements):
        self.verify_calls += 1
        return VerifyResponse(is_valid=True, payer=PAY_TO)

    def settle_payment(self, payload, requirements):
        self.settle_calls += 1
        return SettleResponse(
            success=self.settlement_success,
            error_reason=None if self.settlement_success else "synthetic settlement failure",
            transaction="0xsynthetic" if self.settlement_success else "",
            network=NETWORK,
        )


def payment_context(accepts):
    payload = PaymentPayload(
        payload={"signature": "synthetic-no-chain-call"},
        accepted=accepts[0],
    )
    meta = SimpleNamespace(model_extra={
        MCP_PAYMENT_META_KEY: payload.model_dump(by_alias=True, exclude_none=True),
    })
    return SimpleNamespace(request_context=SimpleNamespace(meta=meta))


class X402PaymentWrapperTests(unittest.IsolatedAsyncioTestCase):
    def make_tool(self, resource_server):
        handler_calls = []

        async def diagnose_failure(error, system="mcp"):
            handler_calls.append(error)
            return json.dumps(diagnose(error, system))

        wrapped = create_payment_wrapper(
            resource_server,
            accepts=resource_server.accepts,
            resource=ResourceInfo(
                url="mcp://tool/diagnose_failure",
                description="Synthetic paid-diagnosis test",
                mime_type="application/json",
            ),
            extensions=payment_discovery_extension(),
        )(diagnose_failure)
        return wrapped, handler_calls

    async def test_success_returns_diagnosis_only_after_settlement(self):
        server = FakeResourceServer(settlement_success=True)
        tool, handler_calls = self.make_tool(server)
        marker = "HTTP 429 synthetic-diagnostic-marker"

        result = await tool(error=marker, system="http", ctx=payment_context(server.accepts))

        self.assertEqual(handler_calls, [marker])
        self.assertEqual(server.verify_calls, 1)
        self.assertEqual(server.settle_calls, 1)
        self.assertFalse(result.isError)
        self.assertEqual(json.loads(result.content[0].text)["category"], "rate_limit")
        self.assertTrue(result.meta[MCP_PAYMENT_RESPONSE_META_KEY]["success"])

    async def test_failed_settlement_withholds_diagnosis_result(self):
        server = FakeResourceServer(settlement_success=False)
        tool, handler_calls = self.make_tool(server)
        marker = "HTTP 429 private-diagnostic-marker"

        result = await tool(error=marker, system="http", ctx=payment_context(server.accepts))

        self.assertEqual(handler_calls, [marker])
        self.assertEqual(server.verify_calls, 1)
        self.assertEqual(server.settle_calls, 1)
        self.assertTrue(result.isError)
        self.assertNotIn(marker, result.content[0].text)
        self.assertIn("Payment settlement failed", result.content[0].text)
        failure = json.loads(result.content[0].text)
        self.assertFalse(failure[MCP_PAYMENT_RESPONSE_META_KEY]["success"])

    async def test_missing_payment_does_not_execute_or_settle(self):
        server = FakeResourceServer(settlement_success=True)
        tool, handler_calls = self.make_tool(server)

        empty_meta = SimpleNamespace(model_extra={})
        context = SimpleNamespace(request_context=SimpleNamespace(meta=empty_meta))
        result = await tool(error="HTTP 429", system="http", ctx=context)

        self.assertEqual(handler_calls, [])
        self.assertEqual(server.verify_calls, 0)
        self.assertEqual(server.settle_calls, 0)
        self.assertTrue(result.isError)
        self.assertIn("Payment Required", result.content[0].text)
        payment_required = result.structuredContent
        self.assertIsInstance(payment_required, dict)
        self.assertIn("extensions", payment_required)
        self.assertIn("bazaar", payment_required["extensions"])
        discovery = payment_required["extensions"]["bazaar"]["info"]["input"]
        self.assertEqual(discovery["type"], "mcp")
        self.assertEqual(discovery["toolName"], "diagnose_failure")
        self.assertEqual(discovery["transport"], "streamable-http")
        error_schema = discovery["inputSchema"]["properties"]["error"]
        self.assertEqual(error_schema["maxLength"], 8000)


if __name__ == "__main__":
    unittest.main()
