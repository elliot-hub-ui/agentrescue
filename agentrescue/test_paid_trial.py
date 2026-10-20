import json
import unittest
from unittest import mock

from starlette.testclient import TestClient

from paid_trial_app import (
    CDP_FACILITATOR_URL,
    MAINNET,
    TESTNET,
    app,
    payment_facilitator_config,
    payment_resource_config,
    payment_settings,
)


class PaidTrialConfigTests(unittest.TestCase):
    def test_payments_are_off_by_default(self):
        self.assertIsNone(payment_settings({}))

    def test_test_mode_accepts_only_base_sepolia_with_a_receiving_address(self):
        env = {
            "AGENTRESCUE_X402_ENABLED": "1",
            "AGENTRESCUE_X402_TEST_MODE": "1",
            "AGENTRESCUE_X402_NETWORK": TESTNET,
            "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
        }
        settings = payment_settings(env)
        self.assertEqual(settings["network"], TESTNET)
        self.assertEqual(settings["mode"], "testnet")

    def test_production_mode_requires_base_mainnet_and_a_receiving_address(self):
        env = {
            "AGENTRESCUE_X402_ENABLED": "true",
            "AGENTRESCUE_X402_NETWORK": MAINNET,
            "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
            "AGENTRESCUE_X402_PRODUCTION_APPROVED": "1",
            "AGENTRESCUE_X402_FACILITATOR": "https://facilitator.example.test",
        }
        self.assertEqual(payment_settings(env)["mode"], "mainnet")

    def test_mainnet_requires_explicit_approval_and_facilitator(self):
        env = {
            "AGENTRESCUE_X402_ENABLED": "1",
            "AGENTRESCUE_X402_NETWORK": MAINNET,
            "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
            "AGENTRESCUE_X402_FACILITATOR": "https://facilitator.example.test",
        }
        with self.assertRaisesRegex(RuntimeError, "PRODUCTION_APPROVED"):
            payment_settings(env)
        approved = {**env, "AGENTRESCUE_X402_PRODUCTION_APPROVED": "1"}
        with self.assertRaisesRegex(RuntimeError, "explicitly selected facilitator"):
            payment_settings({**approved, "AGENTRESCUE_X402_FACILITATOR": ""})

    def test_mainnet_rejects_test_facilitator_and_embedded_credentials(self):
        env = {
            "AGENTRESCUE_X402_ENABLED": "1",
            "AGENTRESCUE_X402_NETWORK": MAINNET,
            "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
            "AGENTRESCUE_X402_PRODUCTION_APPROVED": "1",
            "AGENTRESCUE_X402_FACILITATOR": "https://x402.org/facilitator",
        }
        with self.assertRaisesRegex(RuntimeError, "reserved here for testnet"):
            payment_settings(env)
        with self.assertRaisesRegex(RuntimeError, "without embedded credentials"):
            payment_settings({
                **env,
                "AGENTRESCUE_X402_FACILITATOR": "https://user:secret@facilitator.example.test",
            })
        self.assertEqual(
            payment_settings({
                **env,
                "AGENTRESCUE_X402_FACILITATOR": "https://facilitator.example.test",
            })["facilitator_url"],
            "https://facilitator.example.test",
        )

    def test_cdp_facilitator_requires_api_credentials(self):
        settings = {"facilitator_url": CDP_FACILITATOR_URL}
        with self.assertRaisesRegex(RuntimeError, "CDP_API_KEY_ID and CDP_API_KEY_SECRET"):
            payment_facilitator_config(settings, {})

    def test_cdp_facilitator_uses_official_authenticated_config(self):
        import sys
        from types import ModuleType

        fake_cdp = ModuleType("cdp")
        fake_cdp.__path__ = []
        fake_x402 = ModuleType("cdp.x402")
        expected = object()
        fake_x402.create_facilitator_config = mock.Mock(return_value=expected)
        env = {"CDP_API_KEY_ID": "test-id", "CDP_API_KEY_SECRET": "test-secret"}
        with mock.patch.dict(sys.modules, {"cdp": fake_cdp, "cdp.x402": fake_x402}):
            self.assertIs(payment_facilitator_config(
                {"facilitator_url": CDP_FACILITATOR_URL}, env
            ), expected)
        fake_x402.create_facilitator_config.assert_called_once_with()

    def test_custom_facilitator_keeps_explicit_url_config(self):
        settings = {"facilitator_url": "https://facilitator.example.test"}
        config = payment_facilitator_config(settings, {})
        self.assertEqual(config.url, settings["facilitator_url"])

    def test_enabled_mode_fails_closed_without_network_or_payee(self):
        with self.assertRaises(RuntimeError):
            payment_settings({"AGENTRESCUE_X402_ENABLED": "1"})
        with self.assertRaises(RuntimeError):
            payment_settings({
                "AGENTRESCUE_X402_ENABLED": "1",
                "AGENTRESCUE_X402_NETWORK": MAINNET,
            })

    def test_network_must_match_explicit_mode(self):
        with self.assertRaises(RuntimeError):
            payment_settings({
                "AGENTRESCUE_X402_ENABLED": "1",
                "AGENTRESCUE_X402_TEST_MODE": "1",
                "AGENTRESCUE_X402_NETWORK": MAINNET,
                "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
            })

    def test_zero_or_malformed_payee_is_rejected(self):
        for address in ("0x" + "0" * 40, "0x1234", "not-an-address"):
            with self.subTest(address=address), self.assertRaises(RuntimeError):
                payment_settings({
                    "AGENTRESCUE_X402_ENABLED": "1",
                    "AGENTRESCUE_X402_NETWORK": MAINNET,
                    "AGENTRESCUE_X402_PAY_TO": address,
                })

    def test_payment_resource_config_matches_pinned_x402_sdk_schema(self):
        settings = {
            "network": MAINNET,
            "pay_to": "0x1111111111111111111111111111111111111111",
        }
        config = payment_resource_config(settings)
        self.assertEqual(config.network, MAINNET)
        self.assertEqual(config.pay_to, settings["pay_to"])
        self.assertEqual(config.price, "$0.01")
        self.assertEqual(config.extra, {"name": "USDC", "version": "2"})

    def test_mcp_lists_tool_for_free_then_returns_no_charge_diagnosis(self):
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        with mock.patch.dict("os.environ", {"AGENTRESCUE_X402_ENABLED": "0"}, clear=False):
            with TestClient(app, base_url="http://agentrescue-mcp.onrender.com") as client:
                discovery_headers = {
                    **headers,
                    "MCP-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "server/discover",
                }
                discovered = client.post("/mcp", headers=discovery_headers, json={
                    "jsonrpc": "2.0",
                    "id": "discover-1",
                    "method": "server/discover",
                    "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
                })
                self.assertEqual(discovered.status_code, 200, discovered.text)
                discovery = discovered.json()["result"]
                self.assertEqual(discovery["supportedVersions"], ["2025-11-25", "2025-06-18", "2025-03-26"])
                self.assertIn("paid trial is currently disabled", discovery["instructions"])

                unsupported = client.post("/mcp", headers={
                    **headers,
                    "MCP-Protocol-Version": "2026-07-28",
                    "Mcp-Method": "server/discover",
                }, json={
                    "jsonrpc": "2.0",
                    "id": "discover-unsupported",
                    "method": "server/discover",
                    "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"}},
                })
                self.assertEqual(unsupported.status_code, 400, unsupported.text)
                self.assertEqual(unsupported.json()["error"]["code"], -32022)

                invalid_host = client.post("/mcp", headers={
                    **discovery_headers,
                    "Host": "attacker.example",
                }, json={
                    "jsonrpc": "2.0",
                    "id": "discover-invalid-host",
                    "method": "server/discover",
                    "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
                })
                self.assertEqual(invalid_host.status_code, 421)

                initialized = client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "agentrescue-test", "version": "1.0"},
                    },
                })
                self.assertEqual(initialized.status_code, 200, initialized.text)
                negotiated = initialized.json()["result"]["protocolVersion"]
                request_headers = {**headers, "MCP-Protocol-Version": negotiated}
                listed = client.post("/mcp", headers=request_headers, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
                })
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertEqual(listed.json()["result"]["tools"][0]["name"], "diagnose_failure")
                called = client.post("/mcp", headers=request_headers, json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "diagnose_failure",
                        "arguments": {"error": "HTTP 429 rate limit", "system": "http"},
                    },
                })
                self.assertEqual(called.status_code, 200, called.text)
                result = called.json()["result"]
                self.assertFalse(result.get("isError", False))
                diagnosis = json.loads(result["content"][0]["text"])
                self.assertEqual(diagnosis["category"], "rate_limit")
                self.assertEqual(diagnosis["payment"]["mode"], "disabled")
                rejected = client.get("/mcp", headers={"Host": "attacker.example"})
                self.assertEqual(rejected.status_code, 421)


if __name__ == "__main__":
    unittest.main()
