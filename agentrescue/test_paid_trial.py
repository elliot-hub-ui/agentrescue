import unittest

from paid_trial_app import MAINNET, TESTNET, payment_settings


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


if __name__ == "__main__":
    unittest.main()
