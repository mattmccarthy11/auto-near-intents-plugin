from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from auto_near_intents.verifier import (
    DRY_STATUS_POLICY,
    REQUIRED_FILES,
    ROUTE_FIELD_NAMES,
    SUPPORTED_DEPOSIT_MODES,
    SUPPORTED_DEPOSIT_TYPES,
    SUPPORTED_RECIPIENT_TYPES,
    SUPPORTED_REFUND_TYPES,
    SUPPORTED_SWAP_TYPES,
    audit_publication,
    build_phase1_artifacts,
    ingest_proof_ledger_row,
    validate_demo_schemas,
    verify_demo,
)


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
        check_names = {item["name"] for item in payload["checks"]}
        self.assertIn("near_1click_quote_enums_cover_current_docs", check_names)
        self.assertIn("mock_status_refund_receipt_is_dry_policy_not_real_swap", check_names)
        self.assertIn("public_export_has_no_route_metadata_leaks", check_names)
        self.assertIn("schemas_validate_artifacts", check_names)

    def test_phase1_builder_materializes_dry_quote_and_status_refund_artifacts(self) -> None:
        tracked_quote_before = (EXAMPLES / "near-quote-request.json").read_text(encoding="utf-8")
        tracked_status_before = (EXAMPLES / "mock-near-status-refund-receipt.json").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp_examples = Path(tmp) / "examples"
            shutil.copytree(EXAMPLES, temp_examples)
            payload = build_phase1_artifacts(temp_examples)
            self.assertTrue(payload["ok"], payload)
            self.assertFalse(payload["spendful"])
            self.assertFalse(payload["live_near_transaction"])
            self.assertEqual(payload["quote_dry"], True)
            self.assertEqual(payload["status"], DRY_STATUS_POLICY)
            self.assertTrue((temp_examples / "near-quote-request.json").is_file())
            self.assertTrue((temp_examples / "mock-near-status-refund-receipt.json").is_file())
            self.assertEqual(
                (temp_examples / "near-quote-request.json").read_text(encoding="utf-8"),
                tracked_quote_before,
            )
            self.assertEqual(
                (temp_examples / "mock-near-status-refund-receipt.json").read_text(encoding="utf-8"),
                tracked_status_before,
            )
        self.assertEqual((EXAMPLES / "near-quote-request.json").read_text(encoding="utf-8"), tracked_quote_before)
        self.assertEqual(
            (EXAMPLES / "mock-near-status-refund-receipt.json").read_text(encoding="utf-8"),
            tracked_status_before,
        )

    def test_public_dashboard_exposes_settlement_refund_confidentiality_and_proof(self) -> None:
        dashboard = json.loads((EXAMPLES / "public-dashboard.json").read_text(encoding="utf-8"))
        section = dashboard["near_confidential_research_intent"]
        self.assertIn("settlement", section)
        self.assertIn("refund", section)
        self.assertIn("confidentiality", section)
        self.assertIn("proof_status", section)
        self.assertFalse(section["settlement"]["live_near_transaction"])
        self.assertFalse(section["settlement"]["spendful"])
        self.assertTrue(section["refund"]["route_redacted"])

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

    def test_public_exports_do_not_include_route_metadata(self) -> None:
        intent = json.loads((EXAMPLES / "research-intent.json").read_text(encoding="utf-8"))
        public_dashboard = (EXAMPLES / "public-dashboard.json").read_text(encoding="utf-8")
        public_proof = (EXAMPLES / "public-redacted-proof.json").read_text(encoding="utf-8")
        public_text = public_dashboard + public_proof
        for field in ROUTE_FIELD_NAMES:
            with self.subTest(field=field):
                self.assertNotIn(f'"{field}"', public_text)
        adapter = intent["near_1click_adapter"]
        for field in ROUTE_FIELD_NAMES:
            value = adapter.get(field)
            if isinstance(value, str):
                with self.subTest(value=value):
                    self.assertNotIn(value, public_text)

    def test_compute_tranches_are_capped_and_no_live_release(self) -> None:
        policy = json.loads((EXAMPLES / "compute-tranche-policy.json").read_text(encoding="utf-8"))
        total = sum(item["max_release_usdc"] for item in policy["tranches"])
        self.assertLessEqual(total, policy["max_compute_budget_usdc"])
        self.assertFalse(policy["live_release_enabled"])
        self.assertTrue(all(item["live_release_enabled"] is False for item in policy["tranches"]))

    def test_near_1click_quote_request_is_dry_and_policy_bound(self) -> None:
        quote = json.loads((EXAMPLES / "near-quote-request.json").read_text(encoding="utf-8"))
        policy = json.loads((EXAMPLES / "compute-tranche-policy.json").read_text(encoding="utf-8"))
        body = quote["quoteRequest"]
        self.assertEqual(quote["schema"], "auto-near-1click-quote-request/v1")
        self.assertEqual(quote["compute_tranche_policy_id"], policy["policy_id"])
        self.assertTrue(quote["dry"])
        self.assertTrue(body["dry"])
        self.assertFalse(quote["spendful"])
        self.assertFalse(quote["live_near_transaction"])
        self.assertEqual(body["swapType"], "EXACT_INPUT")
        self.assertEqual(body["depositMode"], "SIMPLE")
        self.assertEqual(body["depositType"], "CONFIDENTIAL_INTENTS")
        self.assertEqual(body["recipientType"], "CONFIDENTIAL_INTENTS")
        self.assertEqual(body["refundType"], "CONFIDENTIAL_INTENTS")
        self.assertEqual(body["confidentiality"], "basic")

    def test_near_1click_quote_model_covers_current_doc_enums(self) -> None:
        self.assertTrue({"FLEX_INPUT", "ANY_INPUT"}.issubset(SUPPORTED_SWAP_TYPES))
        self.assertIn("CONFIDENTIAL_INTENTS", SUPPORTED_DEPOSIT_TYPES)
        self.assertIn("CONFIDENTIAL_INTENTS", SUPPORTED_RECIPIENT_TYPES)
        self.assertIn("CONFIDENTIAL_INTENTS", SUPPORTED_REFUND_TYPES)
        self.assertTrue({"SIMPLE", "MEMO"}.issubset(SUPPORTED_DEPOSIT_MODES))

    def test_mock_status_refund_receipt_has_no_live_deposit(self) -> None:
        receipt = json.loads((EXAMPLES / "mock-near-status-refund-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema"], "auto-near-1click-status-refund-receipt/v1")
        self.assertEqual(receipt["status"], DRY_STATUS_POLICY)
        self.assertIsNone(receipt["near_status"])
        self.assertEqual(receipt["mode"], "mock")
        self.assertFalse(receipt["spendful"])
        self.assertFalse(receipt["live_near_transaction"])
        self.assertFalse(receipt["status_endpoint_called"])
        self.assertFalse(receipt["deposit_submitted"])
        self.assertIsNone(receipt["depositAddress"])
        self.assertIsNone(receipt["depositMemo"])
        self.assertEqual(receipt["refund"]["refundPolicyReason"], "PROOF_NOT_VERIFIED_IN_DRY_RUN")
        self.assertEqual(receipt["refund"]["policy_status"], "mock_refundable_if_proof_fails")
        self.assertNotIn("refundedAmount", receipt["refund"])
        self.assertIsNone(receipt["refund"]["actualRefundedAmount"])

    def test_demo_artifacts_validate_against_schemas(self) -> None:
        payload = validate_demo_schemas(EXAMPLES, ROOT / "schemas")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])

    def test_ingest_auto_token_proof_ledger_row_updates_dry_public_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_examples = Path(tmp) / "examples"
            shutil.copytree(EXAMPLES, temp_examples)
            auto_row = {
                "schema": "auto-proof-ledger-row/v1",
                "proof_ledger_row_id": "auto-token-proof-run-abcdef123456",
                "run_id": "auto-token-proof-run",
                "artifact_sha256": "a" * 64,
                "provider": "venice",
                "result": {
                    "status": "complete",
                    "verification_status": "pending_mock_verification",
                },
                "cost": {
                    "mode": "dry_run",
                    "observed_live_spend_usdc": 0,
                    "credits": 0,
                },
                "source": {
                    "system": "auto-token",
                    "public_record": True,
                },
                "spendful": False,
                "live_near_transaction": False,
            }
            source = Path(tmp) / "auto-proof-ledger-row.json"
            source.write_text(json.dumps(auto_row), encoding="utf-8")

            payload = ingest_proof_ledger_row(temp_examples, source)

            self.assertTrue(payload["ok"], payload)
            self.assertFalse(payload["spendful"])
            self.assertFalse(payload["live_near_transaction"])
            self.assertEqual(payload["intent_id"], "auto-near-intent-demo-001")
            self.assertEqual(payload["settlement_id"], "near-mock-settlement-demo-001")
            self.assertEqual(payload["quote_request_id"], "near-1click-dry-quote-demo-001")
            self.assertEqual(payload["status_refund_receipt_id"], "near-1click-mock-status-refund-demo-001")
            self.assertEqual(payload["proof_ledger_row_id"], auto_row["proof_ledger_row_id"])
            self.assertEqual(payload["run_id"], auto_row["run_id"])
            self.assertEqual(payload["artifact_sha256"], auto_row["artifact_sha256"])
            proof_link = json.loads((temp_examples / "intent-proof-link.json").read_text(encoding="utf-8"))
            dashboard = json.loads((temp_examples / "public-dashboard.json").read_text(encoding="utf-8"))
            redacted = json.loads((temp_examples / "public-redacted-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(proof_link["proof_ledger_row_id"], auto_row["proof_ledger_row_id"])
            self.assertEqual(proof_link["run_id"], auto_row["run_id"])
            self.assertEqual(proof_link["artifact_sha256"], auto_row["artifact_sha256"])
            self.assertEqual(
                dashboard["near_confidential_research_intent"]["proof_status"]["proof_ledger_row_id"],
                auto_row["proof_ledger_row_id"],
            )
            self.assertEqual(redacted["proof"]["run_id"], auto_row["run_id"])
            public_text = json.dumps(dashboard, sort_keys=True) + json.dumps(redacted, sort_keys=True)
            self.assertNotIn("auto-token/data", public_text)
            self.assertNotIn(str(Path(tmp)), public_text)
            verify_payload = verify_demo(temp_examples)
            self.assertTrue(verify_payload["ok"], verify_payload)

    def test_publication_audit_has_no_private_auto_internals_or_secrets(self) -> None:
        payload = audit_publication(ROOT)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])


if __name__ == "__main__":
    unittest.main()
