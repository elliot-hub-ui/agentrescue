import importlib.util
import json
import unittest
import tempfile
import xml.etree.ElementTree as ET
from unittest import mock

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from app import VERSION
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

    def test_agent_setup_docs_expose_absolute_endpoints(self):
        client = TestClient(app, base_url="http://agentrescue-mcp.onrender.com")
        guide = client.get("/llms.txt").text
        homepage = client.get("/").text
        developer_page = client.get("/developers")
        pricing_page = client.get("/pricing")
        robots = client.get("/robots.txt")
        sitemap = client.get("/sitemap.xml")
        openapi = client.get("/openapi.json").json()

        self.assertIn("https://agentrescue-mcp.onrender.com/mcp", guide)
        self.assertIn("https://agentrescue-mcp.onrender.com/v1/diagnose", guide)
        self.assertIn("https://agentrescue-mcp.onrender.com/openapi.json", guide)
        self.assertIn("## When to use", guide)
        self.assertIn("https://agentrescue-mcp.onrender.com/developers", guide)
        self.assertIn("https://agentrescue-mcp.onrender.com/pricing", guide)
        self.assertIn("href='/developers'", homepage)
        self.assertIn("href='/pricing'", homepage)
        self.assertIn("https://agentrescue-mcp.onrender.com/mcp", homepage)
        jsonld = homepage.split("<script type='application/ld+json'>", 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(jsonld)["@type"], "SoftwareApplication")
        self.assertIn("/v1/diagnose", developer_page.text)
        self.assertIn("diagnose_failure", developer_page.text)
        self.assertEqual(developer_page.status_code, 200)
        self.assertIn("Diagnosis is free today", pricing_page.text)
        self.assertIn("$0.01 USDC", pricing_page.text)
        self.assertIn("This price is not active today", pricing_page.text)
        self.assertEqual(pricing_page.status_code, 200)
        self.assertIn("Sitemap: https://agentrescue-mcp.onrender.com/sitemap.xml", robots.text)
        self.assertEqual(robots.status_code, 200)
        urls = ET.fromstring(sitemap.content).findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        self.assertEqual(sitemap.status_code, 200)
        self.assertTrue(any(url.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc", "").endswith("/developers") for url in urls))
        self.assertTrue(all(url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod") is not None for url in urls))
        self.assertEqual(
            openapi["servers"],
            [{"url": "https://agentrescue-mcp.onrender.com"}],
        )

    def test_homepage_negotiates_markdown_and_varies_on_accept(self):
        client = TestClient(app, base_url="http://agentrescue-mcp.onrender.com")
        markdown = client.get("/", headers={"Accept": "text/markdown"})
        html = client.get("/", headers={"Accept": "text/html"})
        self.assertEqual(markdown.status_code, 200)
        self.assertEqual(markdown.headers["content-type"], "text/markdown; charset=utf-8")
        self.assertEqual(markdown.headers["vary"], "Accept")
        self.assertIn("# AgentRescue", markdown.text)
        self.assertIn("/v1/diagnose", markdown.text)
        self.assertEqual(html.status_code, 200)
        self.assertTrue(html.headers["content-type"].startswith("text/html"))
        self.assertEqual(html.headers["vary"], "Accept")
        self.assertIn("<h1>Safer next steps for failing agents.</h1>", html.text)

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
                self.assertEqual(discovery["_meta"]["io.modelcontextprotocol/serverInfo"]["version"], VERSION)
                self.assertEqual(discovery["supportedVersions"], ["2025-11-25", "2025-06-18", "2025-03-26"])
                self.assertIn("paid trial is currently disabled", discovery["instructions"])
                self.assertIn("latest request", discovery["instructions"])
                self.assertIn("human approval", discovery["instructions"])

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
                initialize_result = initialized.json()["result"]
                negotiated = initialize_result["protocolVersion"]
                self.assertEqual(initialize_result["serverInfo"]["version"], VERSION)
                self.assertIn("resources", initialize_result["capabilities"])
                self.assertIn("latest request", initialize_result["instructions"])
                request_headers = {**headers, "MCP-Protocol-Version": negotiated}
                listed = client.post("/mcp", headers=request_headers, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
                })
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertEqual(listed.json()["result"]["tools"][0]["name"], "diagnose_failure")
                tool_description = listed.json()["result"]["tools"][0]["description"]
                self.assertIn("latest request", tool_description)
                self.assertIn("never executes fixes", tool_description)
                resources = client.post("/mcp", headers=request_headers, json={
                    "jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {},
                })
                self.assertEqual(resources.status_code, 200, resources.text)
                resource_uri = "agentrescue://guide/diagnosis"
                self.assertIn(resource_uri, [item["uri"] for item in resources.json()["result"]["resources"]])
                resource = client.post("/mcp", headers=request_headers, json={
                    "jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": resource_uri},
                })
                self.assertEqual(resource.status_code, 200, resource.text)
                guide_text = resource.json()["result"]["contents"][0]["text"]
                self.assertIn("Never send credentials or personal data", guide_text)
                self.assertIn("High-risk advice requires human approval", guide_text)
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


    def test_feedback_is_disabled_by_default(self):
        with mock.patch.dict("os.environ", {"AGENTRESCUE_FEEDBACK_ENABLED": "0"}, clear=False):
            with mock.patch("paid_trial_app._allow", return_value=True):
                response = TestClient(app, base_url="http://agentrescue-mcp.onrender.com").post(
                    "/v1/feedback", json={"opt_in": True, "category": "rate_limit"}
                )
        self.assertEqual(response.status_code, 404)

    def test_feedback_requires_opt_in_rejects_raw_fields_and_stores_only_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            feedback_path = directory + "/feedback.jsonl"
            env = {
                "AGENTRESCUE_FEEDBACK_ENABLED": "1",
                "AGENTRESCUE_FEEDBACK_PATH": feedback_path,
            }
            with mock.patch.dict("os.environ", env, clear=False):
                with mock.patch("paid_trial_app._allow", return_value=True):
                    client = TestClient(app, base_url="http://agentrescue-mcp.onrender.com")
                    no_opt_in = client.post("/v1/feedback", json={"category": "rate_limit"})
                    raw_text = client.post("/v1/feedback", json={
                        "opt_in": True,
                        "category": "rate_limit",
                        "outcome": "resolved",
                        "error": "token=sk_live_do_not_store_12345678",
                    })
                    invalid_category = client.post("/v1/feedback", json={
                        "opt_in": True, "category": "raw diagnostic", "outcome": "resolved",
                    })
                    accepted = client.post("/v1/feedback", json={
                        "opt_in": True, "category": "rate_limit", "outcome": "resolved",
                    })

            self.assertEqual(no_opt_in.status_code, 400)
            self.assertEqual(raw_text.status_code, 400)
            self.assertEqual(invalid_category.status_code, 400)
            self.assertEqual(accepted.status_code, 201, accepted.text)
            with open(feedback_path, encoding="utf-8") as stream:
                stored = json.loads(stream.read())
            self.assertEqual(set(stored), {"category", "outcome", "at"})
            self.assertEqual(stored["category"], "rate_limit")
            self.assertEqual(stored["outcome"], "resolved")
            self.assertNotIn("sk_live_do_not_store_12345678", json.dumps(stored))


if __name__ == "__main__":
    unittest.main()
