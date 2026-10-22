import importlib.util
import json
import unittest
from unittest import mock

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from paid_trial_app import (
    MAINNET,
    TESTNET,
    app,
    diagnose_http,
    http_payment_middleware,
    http_payment_routes,
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

    def test_http_bazaar_route_declares_json_input_and_fixed_price(self):
        settings = {
            "network": TESTNET,
            "pay_to": "0x1111111111111111111111111111111111111111",
            "mode": "testnet",
            "facilitator_url": "https://x402.org/facilitator",
        }
        route = http_payment_routes(settings)["POST /v1/diagnose"]
        self.assertEqual(route["accepts"]["price"], "$0.01")
        self.assertEqual(route["accepts"]["network"], TESTNET)
        bazaar = route["extensions"]["bazaar"]
        self.assertEqual(bazaar["info"]["input"]["bodyType"], "json")
        self.assertEqual(bazaar["info"]["input"]["body"]["error"], "HTTP 429 rate limit")
        self.assertIn("output", bazaar["info"])
        output = bazaar["info"]["output"]
        self.assertEqual(output["example"]["payment"], {
            "mode": "x402-testnet",
            "price_usd": "0.01",
        })
        output_schema = bazaar["schema"]["properties"]["output"]["properties"]["example"]
        self.assertIn("confidence_basis", output_schema["properties"])
        self.assertIn("evidence", output_schema["properties"])
        self.assertEqual(
            set(output_schema["required"]),
            {
                "system", "category", "summary", "confidence", "confidence_basis",
                "recovery", "evidence", "payment",
            },
        )
        self.assertEqual(
            output_schema["properties"]["payment"]["properties"]["mode"]["enum"],
            ["x402-testnet", "x402-mainnet"],
        )

    @unittest.skipUnless(
        importlib.util.find_spec("fastapi"),
        "FastAPI is a pinned dependency of the paid HTTP middleware and is installed in CI",
    )
    def test_unpaid_http_diagnosis_returns_402_with_bazaar_metadata_without_running_diagnosis(self):
        from x402.http import decode_payment_required_header
        from x402.schemas import SupportedKind, SupportedResponse

        settings = {
            "network": TESTNET,
            "pay_to": "0x1111111111111111111111111111111111111111",
            "mode": "testnet",
            "facilitator_url": "https://x402.org/facilitator",
        }

        class FakeFacilitator:
            def __init__(self, config):
                self.config = config

            def get_supported(self):
                return SupportedResponse(kinds=[
                    SupportedKind(x402_version=2, scheme="exact", network=TESTNET)
                ])

        with mock.patch("x402.http.HTTPFacilitatorClient", FakeFacilitator):
            payment_middleware = http_payment_middleware(settings)
            paid_app = Starlette(
                routes=[Route("/v1/diagnose", diagnose_http, methods=["POST"])],
                middleware=[payment_middleware],
            )
            with mock.patch("paid_trial_app.diagnose", side_effect=AssertionError("diagnosis must wait for payment")):
                response = TestClient(paid_app).post(
                    "/v1/diagnose", json={"error": "HTTP 429 rate limit"}
                )

        self.assertEqual(response.status_code, 402, response.text)
        self.assertIn("PAYMENT-REQUIRED", response.headers)
        required = decode_payment_required_header(response.headers["PAYMENT-REQUIRED"])
        self.assertIn("bazaar", required.extensions)
        self.assertEqual(required.accepts[0].network, TESTNET)
        self.assertEqual(required.accepts[0].amount, "10000")

    def test_http_diagnosis_is_free_when_payments_are_disabled_and_does_not_echo_input(self):
        error = "HTTP 429 rate limit with token=sk_live_abcdefghijklmnop123456"
        with mock.patch.dict("os.environ", {"AGENTRESCUE_X402_ENABLED": "0"}, clear=False):
            response = TestClient(app, base_url="http://agentrescue-mcp.onrender.com").post(
                "/v1/diagnose", json={"error": error}
            )
        self.assertEqual(response.status_code, 200, response.text)
        diagnosis = response.json()
        self.assertEqual(diagnosis["category"], "rate_limit")
        self.assertEqual(diagnosis["payment"], {"mode": "disabled", "price_usd": "0.00"})
        self.assertNotIn("sk_live_abcdefghijklmnop123456", response.text)

    def test_http_diagnosis_rejects_invalid_and_oversized_requests(self):
        with mock.patch.dict("os.environ", {"AGENTRESCUE_X402_ENABLED": "0"}, clear=False):
            client = TestClient(app, base_url="http://agentrescue-mcp.onrender.com")
            invalid_json = client.post("/v1/diagnose", content="{")
            extra_field = client.post("/v1/diagnose", json={"error": "HTTP 429", "secret": "x"})
            invalid_system = client.post("/v1/diagnose", json={"error": "HTTP 429", "system": "shell"})
            too_long = client.post("/v1/diagnose", json={"error": "x" * 8001})
        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(extra_field.status_code, 400)
        self.assertEqual(invalid_system.status_code, 400)
        self.assertEqual(too_long.status_code, 413)

    def test_openapi_documents_http_payment_boundary_and_402_when_enabled(self):
        client = TestClient(app, base_url="http://agentrescue-mcp.onrender.com")
        with mock.patch.dict("os.environ", {"AGENTRESCUE_X402_ENABLED": "0"}, clear=False):
            free_schema = client.get("/openapi.json").json()
        payment_schema = free_schema["components"]["schemas"]["Diagnosis"]["properties"]["payment"]
        self.assertEqual(payment_schema["properties"]["mode"]["enum"][0], "disabled")

        with mock.patch.dict("os.environ", {
            "AGENTRESCUE_X402_ENABLED": "1",
            "AGENTRESCUE_X402_TEST_MODE": "1",
            "AGENTRESCUE_X402_NETWORK": TESTNET,
            "AGENTRESCUE_X402_PAY_TO": "0x1111111111111111111111111111111111111111",
        }, clear=False):
            paid_schema = client.get("/openapi.json").json()
        self.assertIn("402", paid_schema["paths"]["/v1/diagnose"]["post"]["responses"])

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
