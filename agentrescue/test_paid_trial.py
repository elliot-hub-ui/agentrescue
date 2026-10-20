import json
import unittest
from unittest import mock

from starlette.testclient import TestClient

from paid_trial_app import MAINNET, TESTNET, app, payment_settings


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
        }
        self.assertEqual(payment_settings(env)["mode"], "mainnet")

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
