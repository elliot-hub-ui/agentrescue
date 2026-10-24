import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from starlette.testclient import TestClient

from paid_trial_app import app
from stripe_payments import PRICE_CENTS, StripeConfigError, _verify_signature, stripe_settings


class StripeSettingsTests(unittest.TestCase):
    def test_payment_routes_are_off_by_default(self):
        self.assertIsNone(stripe_settings({}))

    def test_live_keys_are_rejected_even_if_feature_flag_is_on(self):
        with self.assertRaises(StripeConfigError):
            stripe_settings({
                "AGENTRESCUE_STRIPE_ENABLED": "1",
                "STRIPE_SECRET_KEY": "sk_live_never-use",
                "STRIPE_WEBHOOK_SECRET": "whsec_test",
                "AGENTRESCUE_PUBLIC_URL": "https://example.test",
            })

    def test_https_origin_and_test_credentials_are_required(self):
        env = {
            "AGENTRESCUE_STRIPE_ENABLED": "1",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_WEBHOOK_SECRET": "whsec_example",
            "AGENTRESCUE_PUBLIC_URL": "http://example.test",
        }
        with self.assertRaises(StripeConfigError):
            stripe_settings(env)

    def test_signature_verification_checks_timestamp_and_digest(self):
        payload = b'{"id":"evt_test"}'
        timestamp = str(int(time.time()))
        secret = "whsec_test"
        digest = hmac.new(secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
        self.assertTrue(_verify_signature(payload, f"t={timestamp},v1={digest}", secret))
        self.assertFalse(_verify_signature(payload, f"t={timestamp},v1={digest}", "wrong-secret"))
        self.assertFalse(_verify_signature(payload, f"t=1,v1={digest}", secret))
        oversized_timestamp = "9" * 5000
        self.assertFalse(_verify_signature(payload, f"t={oversized_timestamp},v1={digest}", secret))


class StripeCheckoutFlowTests(unittest.TestCase):
    def test_paid_webhook_unlocks_exactly_one_diagnosis(self):
        with tempfile.TemporaryDirectory() as folder:
            fake_session = types.SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/session")
            create = mock.Mock(return_value=fake_session)
            fake_client = types.SimpleNamespace(
                v1=types.SimpleNamespace(checkout=types.SimpleNamespace(sessions=types.SimpleNamespace(create=create)))
            )
            stripe_module = types.ModuleType("stripe")
            stripe_module.StripeClient = mock.Mock(return_value=fake_client)
            env = {
                "AGENTRESCUE_STRIPE_ENABLED": "1",
                "STRIPE_SECRET_KEY": "sk_test_example",
                "STRIPE_WEBHOOK_SECRET": "whsec_example",
                "AGENTRESCUE_PUBLIC_URL": "https://agentrescue.test",
                "AGENTRESCUE_STRIPE_DB": os.path.join(folder, "stripe.sqlite3"),
                "AGENTRESCUE_X402_ENABLED": "0",
            }
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.dict(sys.modules, {"stripe": stripe_module}):
                client = TestClient(app)
                created = client.post("/v1/stripe/checkout")
                self.assertEqual(created.status_code, 201, created.text)
                result = created.json()
                self.assertEqual(result["mode"], "test")
                self.assertEqual(result["price_usd"], "1.00")
                self.assertEqual(create.call_args.kwargs["params"]["line_items"][0]["price_data"]["unit_amount"], PRICE_CENTS)
                token = result["access_token"]
                body = {"error": "HTTP 429 rate limit", "system": "http"}
                waiting = client.post("/v1/stripe/diagnose", json=body, headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(waiting.status_code, 402)

                checkout_token_hash = create.call_args.kwargs["params"]["metadata"]["agentrescue_token_hash"]
                event = {
                    "id": "evt_test_paid",
                    "type": "checkout.session.completed",
                    "data": {"object": {
                        "id": "cs_test_123",
                        "livemode": False,
                        "mode": "payment",
                        "payment_status": "paid",
                        "currency": "usd",
                        "amount_total": PRICE_CENTS,
                        "metadata": {"agentrescue_token_hash": checkout_token_hash},
                    }},
                }
                payload = json.dumps(event, separators=(",", ":")).encode()
                timestamp = str(int(time.time()))
                digest = hmac.new(b"whsec_example", timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
                headers = {"Stripe-Signature": f"t={timestamp},v1={digest}"}
                paid = client.post("/v1/stripe/webhook", content=payload, headers=headers)
                self.assertEqual(paid.status_code, 200, paid.text)
                duplicate = client.post("/v1/stripe/webhook", content=payload, headers=headers)
                self.assertTrue(duplicate.json()["duplicate"])

                diagnosed = client.post("/v1/stripe/diagnose", json=body, headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(diagnosed.status_code, 200, diagnosed.text)
                self.assertEqual(diagnosed.json()["category"], "rate_limit")
                used = client.post("/v1/stripe/diagnose", json=body, headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(used.status_code, 402)
                client.close()

    def test_invalid_webhook_signature_cannot_activate_credit(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {
                "AGENTRESCUE_STRIPE_ENABLED": "1",
                "STRIPE_SECRET_KEY": "sk_test_example",
                "STRIPE_WEBHOOK_SECRET": "whsec_example",
                "AGENTRESCUE_PUBLIC_URL": "https://agentrescue.test",
                "AGENTRESCUE_STRIPE_DB": os.path.join(folder, "stripe.sqlite3"),
                "AGENTRESCUE_X402_ENABLED": "0",
            }
            now = str(int(time.time()))
            with mock.patch.dict(os.environ, env, clear=True):
                client = TestClient(app)
                response = client.post(
                    "/v1/stripe/webhook",
                    content=b'{"id":"evt_bad"}',
                    headers={"Stripe-Signature": f"t={now},v1=bad"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "invalid_signature")
                client.close()


if __name__ == "__main__":
    unittest.main()
