from __future__ import annotations

import json
import unittest
from pathlib import Path

from auto_near_intents.verifier import REQUIRED_FILES, verify_demo


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class NearIntentDemoTests(unittest.TestCase):
    def test_required_demo_artifacts_exist(self) -> None:
        for filename in REQUIRED_FILES.values():
            with self.subTest(filename=filename):
                self.assertTrue((EXAMPLES / filename).is_file())

    def test_demo_verifier_passes_all_goal_conditions(self) -> None:
        payload = verify_demo(EXAMPLES)
        self.assertTrue(payload["ok"], payload)
        self.assertFalse(payload["spendful"])
        self.assertFalse(payload["live_near_transaction"])
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual(payload["passed_count"], 7)

    def test_public_dashboard_exposes_settlement_refund_confidentiality_and_proof(self) -> None:
        dashboard = json.loads((EXAMPLES / "public-dashboard.json").read_text(encoding="utf-8"))
        section = dashboard["near_confidential_research_intent"]
        self.assertIn("settlement", section)
        self.assertIn("refund", section)
        self.assertIn("confidentiality", section)
        self.assertIn("proof_status", section)
        self.assertFalse(section["settlement"]["live_near_transaction"])
        self.assertFalse(section["settlement"]["spendful"])

    def test_final_payout_is_blocked_until_proof_verifies(self) -> None:
        settlement = json.loads((EXAMPLES / "mock-near-settlement.json").read_text(encoding="utf-8"))
        proof_link = json.loads((EXAMPLES / "intent-proof-link.json").read_text(encoding="utf-8"))
        self.assertEqual(settlement["final_payout"]["status"], "blocked_until_proof_verified")
        self.assertFalse(settlement["final_payout"]["live_release_enabled"])
        self.assertEqual(proof_link["proof_verification"]["status"], "pending_mock_verification")
        self.assertTrue(proof_link["proof_verification"]["required_before_final_payout"])

    def test_public_exports_do_not_include_private_intent_values(self) -> None:
        intent = json.loads((EXAMPLES / "research-intent.json").read_text(encoding="utf-8"))
        public_dashboard = (EXAMPLES / "public-dashboard.json").read_text(encoding="utf-8")
        public_proof = (EXAMPLES / "public-redacted-proof.json").read_text(encoding="utf-8")
        public_text = public_dashboard + public_proof
        for field in intent["confidentiality"]["private_fields"]:
            with self.subTest(field=field):
                self.assertNotIn(field, public_text)
                value = intent
                for part in field.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if isinstance(value, (str, int, float)):
                    self.assertNotIn(str(value), public_text)

    def test_compute_tranches_are_capped_and_no_live_release(self) -> None:
        policy = json.loads((EXAMPLES / "compute-tranche-policy.json").read_text(encoding="utf-8"))
        total = sum(item["max_release_usdc"] for item in policy["tranches"])
        self.assertLessEqual(total, policy["max_compute_budget_usdc"])
        self.assertFalse(policy["live_release_enabled"])
        self.assertTrue(all(item["live_release_enabled"] is False for item in policy["tranches"]))


if __name__ == "__main__":
    unittest.main()
