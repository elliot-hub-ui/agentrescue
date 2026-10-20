import unittest
from types import SimpleNamespace

from x402_mcp_test_once import X402McpSdkAdapter


class FakeMcpSession:
    async def call_tool(self, name, arguments, read_timeout_seconds=None, *, meta=None):
        self.seen = (name, arguments, meta)
        return SimpleNamespace(
            content=[], isError=False, meta={"x402/payment-response": {"success": True}},
            structuredContent={"ok": True},
        )


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_mcp_meta_for_x402_settlement_extractor(self):
        session = FakeMcpSession()
        adapter = X402McpSdkAdapter(session)
        payment = {"x402/payment": {"x402Version": 2}}
        result = await adapter.call_tool(
            {"name": "diagnose_failure", "arguments": {"error": "test"}, "_meta": payment},
            read_timeout_seconds=12,
        )
        self.assertEqual(session.seen[0], "diagnose_failure")
        self.assertEqual(session.seen[2], payment)
        self.assertEqual(result._meta["x402/payment-response"]["success"], True)


if __name__ == "__main__":
    unittest.main()
