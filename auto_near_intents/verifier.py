from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = {
    "intent": "research-intent.json",
    "tranche_policy": "compute-tranche-policy.json",
    "quote_request": "near-quote-request.json",
    "status_refund_receipt": "mock-near-status-refund-receipt.json",
    "settlement": "mock-near-settlement.json",
    "proof_ledger_row": "proof-ledger-row.json",
    "proof_link": "intent-proof-link.json",
    "dashboard": "public-dashboard.json",
    "redacted_proof": "public-redacted-proof.json",
    "export_policy": "public-export-policy.json",
}

SCHEMA_FILES = {
    "intent": "research-intent.schema.json",
    "tranche_policy": "compute-tranche-policy.schema.json",
    "quote_request": "near-quote-request.schema.json",
    "status_refund_receipt": "mock-near-status-refund-receipt.schema.json",
    "settlement": "mock-near-settlement.schema.json",
    "proof_ledger_row": "proof-ledger-row.schema.json",
    "proof_link": "intent-proof-link.schema.json",
    "export_policy": "public-export-policy.schema.json",
}

SUPPORTED_SWAP_TYPES = {"EXACT_INPUT", "EXACT_OUTPUT", "FLEX_INPUT", "ANY_INPUT"}
SUPPORTED_DEPOSIT_TYPES = {"ORIGIN_CHAIN", "INTENTS", "CONFIDENTIAL_INTENTS"}
SUPPORTED_RECIPIENT_TYPES = {"DESTINATION_CHAIN", "INTENTS", "CONFIDENTIAL_INTENTS"}
SUPPORTED_REFUND_TYPES = {"ORIGIN_CHAIN", "INTENTS", "CONFIDENTIAL_INTENTS"}
SUPPORTED_DEPOSIT_MODES = {"SIMPLE", "MEMO"}
SUPPORTED_CONFIDENTIALITY_MODES = {"public", "basic", "advanced"}
DRY_STATUS_POLICY = "NO_DEPOSIT_DRY_RUN"

PUBLIC_ARTIFACT_KEYS = ("dashboard", "redacted_proof")
PRIVATE_VALUE_FIELDS = {
    "private_subject",
    "confidential_prompt",
    "private_dataset_uri",
    "buyer_internal_id",
    "confidential_budget_usdc",
    "settlement_memo_private",
}
PRIVATE_FIELD_NAMES = PRIVATE_VALUE_FIELDS | {
    "private_fields",
    "confidential_fields",
    "private_values",
}
ROUTE_FIELD_NAMES = {
    "recipient",
    "recipientType",
    "refundTo",
    "refundType",
    "depositType",
    "depositMode",
    "depositAddress",
    "depositMemo",
    "virtualChainRecipient",
    "virtualChainRefundRecipient",
    "customRecipientMsg",
}
PUBLICATION_AUDIT_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "dist", "build"}
PUBLICATION_AUDIT_SKIP_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
PUBLICATION_RISK_PATTERNS = {
    "github_token": re.compile(r"gh[opsu]_[A-Za-z0-9_]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "env_private_key": re.compile(r"\b(?:PRIVATE_KEY|NEAR_PRIVATE_KEY)\s*[:=]\s*['\"]?[A-Za-z0-9_/+=-]{16,}", re.IGNORECASE),
    "env_api_key": re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_/+=-]{16,}", re.IGNORECASE),
    "venice_key": re.compile(r"\bVENICE_API_KEY\b"),
    "local_auto_token_path": re.compile(r"/Users/[^\\s'\"`]+/GitHub/auto-token"),
    "auto_token_private_data_path": re.compile(r"\bauto-token/data/(?:runs|live-approvals|agent-sessions|agent-payments)"),
    "real_s3_uri": re.compile(r"\bs3://"),
}


def json_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def validate_json_schema(payload: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    issues: list[str] = []
    if "const" in schema and payload != schema["const"]:
        issues.append(f"{path}: expected const {schema['const']!r}, got {payload!r}")
    if "enum" in schema and payload not in schema["enum"]:
        issues.append(f"{path}: expected one of {schema['enum']!r}, got {payload!r}")
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(json_type_matches(payload, item) for item in expected_type):
            issues.append(f"{path}: expected type {expected_type!r}, got {type(payload).__name__}")
    elif isinstance(expected_type, str) and not json_type_matches(payload, expected_type):
        issues.append(f"{path}: expected type {expected_type!r}, got {type(payload).__name__}")
        return issues
    if isinstance(payload, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in payload:
                    issues.append(f"{path}.{key}: missing required property")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in payload and isinstance(child_schema, dict):
                    issues.extend(validate_json_schema(payload[key], child_schema, f"{path}.{key}"))
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            allowed = set(properties)
            for key in payload:
                if key not in allowed:
                    issues.append(f"{path}.{key}: additional property is not allowed")
    if isinstance(payload, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(payload) < min_items:
            issues.append(f"{path}: expected at least {min_items} items, got {len(payload)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                issues.extend(validate_json_schema(item, item_schema, f"{path}[{index}]"))
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        exclusive_minimum = schema.get("exclusiveMinimum")
        if isinstance(exclusive_minimum, (int, float)) and payload <= exclusive_minimum:
            issues.append(f"{path}: expected > {exclusive_minimum}, got {payload}")
    if isinstance(payload, str) and isinstance(schema.get("pattern"), str):
        if re.fullmatch(schema["pattern"], payload) is None:
            issues.append(f"{path}: value does not match pattern {schema['pattern']!r}")
    return issues


def validate_demo_schemas(root: Path, schema_root: Path | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if schema_root is None:
        candidate = root.parent / "schemas"
        schema_root = candidate if candidate.is_dir() else Path(__file__).resolve().parents[1] / "schemas"
    schema_root = schema_root.expanduser().resolve()
    artifact_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for key, schema_filename in SCHEMA_FILES.items():
        artifact_path = root / REQUIRED_FILES[key]
        schema_path = schema_root / schema_filename
        payload = load_json(artifact_path)
        schema = load_json(schema_path)
        schema_issues = validate_json_schema(payload, schema)
        artifact_results.append(
            {
                "artifact": artifact_path.name,
                "schema": schema_path.name,
                "ok": not schema_issues,
                "issue_count": len(schema_issues),
            }
        )
        for issue in schema_issues:
            issues.append({"artifact": artifact_path.name, "schema": schema_path.name, "issue": issue})
    return {
        "schema": "auto-near-intents-schema-validation/v1",
        "ok": not issues,
        "root": str(root),
        "schema_root": str(schema_root),
        "artifact_count": len(artifact_results),
        "artifacts": artifact_results,
        "issues": issues,
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"top-level JSON value must be an object: {path}")
    return payload


def load_demo(root: Path) -> dict[str, dict[str, Any]]:
    return {key: load_json(root / filename) for key, filename in REQUIRED_FILES.items()}


def find_values(payload: Any, fields: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in fields and isinstance(value, (str, int, float)):
                values.append(str(value))
            values.extend(find_values(value, fields))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(find_values(item, fields))
    return [value for value in values if value]


def find_keys(payload: Any, fields: set[str]) -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in fields:
                keys.append(str(key))
            keys.extend(find_keys(value, fields))
    elif isinstance(payload, list):
        for item in payload:
            keys.extend(find_keys(item, fields))
    return keys


def contains_text(payload: Any, needle: str) -> bool:
    if not needle:
        return False
    if isinstance(payload, dict):
        return any(contains_text(key, needle) or contains_text(value, needle) for key, value in payload.items())
    if isinstance(payload, list):
        return any(contains_text(item, needle) for item in payload)
    return needle in str(payload)


def check(name: str, passed: bool, evidence: dict[str, Any], issue: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
        "issue": None if passed else issue,
    }


def build_quote_request(intent: dict[str, Any], tranche_policy: dict[str, Any]) -> dict[str, Any]:
    adapter = intent.get("near_1click_adapter", {})
    if not isinstance(adapter, dict):
        adapter = {}
    max_compute = int(float(tranche_policy.get("max_compute_budget_usdc", 0) or 0))
    quote_amount = int(adapter.get("amount", 0) or 0)
    if quote_amount <= 0:
        quote_amount = max_compute * 1_000_000
    return {
        "schema": "auto-near-1click-quote-request/v1",
        "quote_request_id": adapter.get("quote_request_id", "near-1click-dry-quote-demo-001"),
        "intent_id": intent.get("intent_id"),
        "compute_tranche_policy_id": tranche_policy.get("policy_id"),
        "provider": "near_1click",
        "endpoint": "https://1click.chaindefuser.com/v0/quote",
        "method": "POST",
        "dry": True,
        "spendful": False,
        "live_near_transaction": False,
        "quoteRequest": {
            "dry": True,
            "swapType": adapter.get("swapType", "EXACT_INPUT"),
            "slippageTolerance": int(adapter.get("slippageTolerance", 100)),
            "originAsset": adapter.get("originAsset", "nep141:wrap.near"),
            "depositType": adapter.get("depositType", "CONFIDENTIAL_INTENTS"),
            "destinationAsset": adapter.get("destinationAsset", "nep141:usdc.near"),
            "amount": str(quote_amount),
            "recipient": adapter.get("recipient", "auto-research-settlement.near"),
            "recipientType": adapter.get("recipientType", "CONFIDENTIAL_INTENTS"),
            "refundTo": adapter.get("refundTo", "auto-research-refund.near"),
            "refundType": adapter.get("refundType", "CONFIDENTIAL_INTENTS"),
            "deadline": intent.get("deadline"),
            "depositMode": adapter.get("depositMode", "SIMPLE"),
            "confidentiality": adapter.get("confidentiality", "basic"),
            "quoteWaitingTimeMs": int(adapter.get("quoteWaitingTimeMs", 5000)),
        },
        "private_fields_forwarded": [],
        "rule": "This adapter emits a 1Click-compatible dry quote request. It does not send the request, sign an intent, deposit funds, or execute a NEAR transaction.",
    }


def build_status_refund_receipt(quote_request: dict[str, Any], settlement: dict[str, Any]) -> dict[str, Any]:
    quote_body = quote_request.get("quoteRequest", {})
    if not isinstance(quote_body, dict):
        quote_body = {}
    return {
        "schema": "auto-near-1click-status-refund-receipt/v1",
        "status_refund_receipt_id": settlement.get(
            "status_refund_receipt_id", "near-1click-mock-status-refund-demo-001"
        ),
        "intent_id": quote_request.get("intent_id"),
        "settlement_id": settlement.get("settlement_id"),
        "provider": "near_1click",
        "endpoint": "https://1click.chaindefuser.com/v0/status",
        "method": "GET",
        "mode": "mock",
        "spendful": False,
        "live_near_transaction": False,
        "status_endpoint_called": False,
        "deposit_submitted": False,
        "depositAddress": None,
        "depositMemo": None,
        "status": DRY_STATUS_POLICY,
        "near_status": None,
        "refund": {
            "policy_status": "mock_refundable_if_proof_fails",
            "refundTo": quote_body.get("refundTo"),
            "refundType": quote_body.get("refundType"),
            "refundPolicyReason": "PROOF_NOT_VERIFIED_IN_DRY_RUN",
            "refundableAmount": quote_body.get("amount"),
            "actualRefundedAmount": None,
        },
        "swapDetails": {
            "intentHashes": [],
            "nearTxHashes": [],
            "originChainTxHashes": [],
            "destinationChainTxHashes": [],
        },
        "rule": "This receipt is a dry status-policy fixture. No deposit address was funded, no status endpoint was called, and no real NEAR swap status is claimed.",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_phase1_artifacts(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    intent = load_json(root / REQUIRED_FILES["intent"])
    tranche_policy = load_json(root / REQUIRED_FILES["tranche_policy"])
    settlement = load_json(root / REQUIRED_FILES["settlement"])
    quote_request = build_quote_request(intent, tranche_policy)
    status_refund_receipt = build_status_refund_receipt(quote_request, settlement)
    write_json(root / REQUIRED_FILES["quote_request"], quote_request)
    write_json(root / REQUIRED_FILES["status_refund_receipt"], status_refund_receipt)
    return {
        "schema": "auto-near-1click-phase1-build/v1",
        "ok": True,
        "spendful": False,
        "live_near_transaction": False,
        "root": str(root),
        "wrote": [
            str(root / REQUIRED_FILES["quote_request"]),
            str(root / REQUIRED_FILES["status_refund_receipt"]),
        ],
        "intent_id": quote_request.get("intent_id"),
        "quote_dry": quote_request.get("quoteRequest", {}).get("dry"),
        "status": status_refund_receipt.get("status"),
    }


def validate_proof_ledger_row(proof_ledger_row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if proof_ledger_row.get("schema") != "auto-proof-ledger-row/v1":
        issues.append("schema must be auto-proof-ledger-row/v1")
    for key in ("proof_ledger_row_id", "run_id", "artifact_sha256"):
        if not proof_ledger_row.get(key):
            issues.append(f"{key} is required")
    artifact_sha = proof_ledger_row.get("artifact_sha256")
    if not isinstance(artifact_sha, str) or re.fullmatch(r"[0-9a-f]{64}", artifact_sha) is None:
        issues.append("artifact_sha256 must be a 64-char lowercase hex digest")
    cost = proof_ledger_row.get("cost", {})
    if not isinstance(cost, dict):
        issues.append("cost must be an object")
        cost = {}
    if cost.get("mode") not in {"dry_run", "dry-run", "mock", "planned"}:
        issues.append("cost.mode must be dry/no-spend")
    if float(cost.get("observed_live_spend_usdc", 0) or 0) != 0:
        issues.append("observed_live_spend_usdc must be 0")
    if proof_ledger_row.get("spendful", False) is not False:
        issues.append("spendful must be false when present")
    if proof_ledger_row.get("live_near_transaction", False) is not False:
        issues.append("live_near_transaction must be false when present")
    return issues


def build_intent_proof_link(
    intent: dict[str, Any],
    settlement: dict[str, Any],
    quote_request: dict[str, Any],
    status_refund_receipt: dict[str, Any],
    proof_ledger_row: dict[str, Any],
) -> dict[str, Any]:
    result = proof_ledger_row.get("result", {})
    if not isinstance(result, dict):
        result = {}
    return {
        "schema": "auto-intent-proof-link/v1",
        "intent_id": intent.get("intent_id"),
        "settlement_id": settlement.get("settlement_id"),
        "quote_request_id": quote_request.get("quote_request_id"),
        "status_refund_receipt_id": status_refund_receipt.get("status_refund_receipt_id"),
        "proof_ledger_row_id": proof_ledger_row.get("proof_ledger_row_id"),
        "run_id": proof_ledger_row.get("run_id"),
        "artifact_sha256": proof_ledger_row.get("artifact_sha256"),
        "proof_verification": {
            "required_before_final_payout": True,
            "status": result.get("verification_status", "pending_mock_verification"),
        },
    }


def update_public_artifacts_from_proof_link(
    dashboard: dict[str, Any],
    redacted_proof: dict[str, Any],
    proof_link: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    verification = proof_link.get("proof_verification", {})
    if not isinstance(verification, dict):
        verification = {}
    status = verification.get("status")
    section = dashboard.setdefault("near_confidential_research_intent", {})
    if not isinstance(section, dict):
        section = {}
        dashboard["near_confidential_research_intent"] = section
    proof_status = section.setdefault("proof_status", {})
    if not isinstance(proof_status, dict):
        proof_status = {}
        section["proof_status"] = proof_status
    proof_status.update(
        {
            "artifact_sha256": proof_link.get("artifact_sha256"),
            "proof_ledger_row_id": proof_link.get("proof_ledger_row_id"),
            "run_id": proof_link.get("run_id"),
            "status": status,
        }
    )
    proof = redacted_proof.setdefault("proof", {})
    if not isinstance(proof, dict):
        proof = {}
        redacted_proof["proof"] = proof
    proof.update(
        {
            "artifact_sha256": proof_link.get("artifact_sha256"),
            "proof_ledger_row_id": proof_link.get("proof_ledger_row_id"),
            "run_id": proof_link.get("run_id"),
            "status": status,
        }
    )
    return dashboard, redacted_proof


def ingest_proof_ledger_row(root: Path, proof_row_path: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    proof_row_path = proof_row_path.expanduser().resolve()
    proof_ledger_row = load_json(proof_row_path)
    issues = validate_proof_ledger_row(proof_ledger_row)
    if issues:
        raise ValueError("invalid proof ledger row: " + "; ".join(issues))
    demo = load_demo(root)
    intent = demo["intent"]
    settlement = demo["settlement"]
    quote_request = demo["quote_request"]
    status_refund_receipt = demo["status_refund_receipt"]
    proof_link = build_intent_proof_link(intent, settlement, quote_request, status_refund_receipt, proof_ledger_row)
    dashboard, redacted_proof = update_public_artifacts_from_proof_link(
        demo["dashboard"], demo["redacted_proof"], proof_link
    )
    write_json(root / REQUIRED_FILES["proof_ledger_row"], proof_ledger_row)
    write_json(root / REQUIRED_FILES["proof_link"], proof_link)
    write_json(root / REQUIRED_FILES["dashboard"], dashboard)
    write_json(root / REQUIRED_FILES["redacted_proof"], redacted_proof)
    return {
        "schema": "auto-near-intents-proof-ledger-ingest/v1",
        "ok": True,
        "spendful": False,
        "live_near_transaction": False,
        "root": str(root),
        "input": str(proof_row_path),
        "wrote": [
            str(root / REQUIRED_FILES["proof_ledger_row"]),
            str(root / REQUIRED_FILES["proof_link"]),
            str(root / REQUIRED_FILES["dashboard"]),
            str(root / REQUIRED_FILES["redacted_proof"]),
        ],
        "intent_id": proof_link.get("intent_id"),
        "settlement_id": proof_link.get("settlement_id"),
        "quote_request_id": proof_link.get("quote_request_id"),
        "status_refund_receipt_id": proof_link.get("status_refund_receipt_id"),
        "proof_ledger_row_id": proof_link.get("proof_ledger_row_id"),
        "run_id": proof_link.get("run_id"),
        "artifact_sha256": proof_link.get("artifact_sha256"),
    }


def verify_demo(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    demo = load_demo(root)
    intent = demo["intent"]
    tranche_policy = demo["tranche_policy"]
    quote_request = demo["quote_request"]
    status_refund_receipt = demo["status_refund_receipt"]
    settlement = demo["settlement"]
    proof_ledger_row = demo["proof_ledger_row"]
    proof_link = demo["proof_link"]
    dashboard = demo["dashboard"]
    redacted_proof = demo["redacted_proof"]
    export_policy = demo["export_policy"]

    intent_id = intent.get("intent_id")
    settlement_id = settlement.get("settlement_id")
    proof_row_id = proof_ledger_row.get("proof_ledger_row_id")
    proof_run_id = proof_ledger_row.get("run_id")
    artifact_hash = proof_ledger_row.get("artifact_sha256")
    tranches = tranche_policy.get("tranches", [])
    tranche_total = sum(float(item.get("max_release_usdc", 0) or 0) for item in tranches if isinstance(item, dict))
    max_compute = float(tranche_policy.get("max_compute_budget_usdc", 0) or 0)

    expected_quote_request = build_quote_request(intent, tranche_policy)
    expected_status_refund_receipt = build_status_refund_receipt(quote_request, settlement)
    schema_validation = validate_demo_schemas(root)
    quote_body = quote_request.get("quoteRequest", {})
    if not isinstance(quote_body, dict):
        quote_body = {}
    refund = status_refund_receipt.get("refund", {})
    if not isinstance(refund, dict):
        refund = {}

    public_values = [dashboard, redacted_proof]
    private_values = find_values(intent, PRIVATE_VALUE_FIELDS)
    public_export_keys = sorted(set(find_keys(public_values, PRIVATE_FIELD_NAMES)))
    leaked_values = sorted(
        value
        for value in private_values
        if any(contains_text(public_artifact, value) for public_artifact in public_values)
    )
    route_values = sorted(set(find_values(intent.get("near_1click_adapter", {}), ROUTE_FIELD_NAMES) + find_values(quote_body, ROUTE_FIELD_NAMES)))
    public_route_keys = sorted(set(find_keys(public_values, ROUTE_FIELD_NAMES)))
    leaked_route_values = sorted(
        value
        for value in route_values
        if any(contains_text(public_artifact, value) for public_artifact in public_values)
    )
    denied_field_names = set(export_policy.get("denied_public_field_names", []))

    settlement_section = dashboard.get("near_confidential_research_intent", {})
    if not isinstance(settlement_section, dict):
        settlement_section = {}
    dashboard_sections = set(settlement_section.keys())

    checks = [
        check(
            "research_intent_exists_and_valid",
            intent.get("schema") == "auto-research-intent/v1"
            and bool(intent_id)
            and intent.get("settlement_provider") == "near_intents"
            and intent.get("confidentiality", {}).get("mode") == "confidential",
            {"intent_id": intent_id, "schema": intent.get("schema")},
            "research-intent.json must be a confidential NEAR research intent",
        ),
        check(
            "compute_tranche_policy_capped",
            tranche_policy.get("schema") == "auto-compute-tranche-policy/v1"
            and tranche_policy.get("intent_id") == intent_id
            and bool(tranche_policy.get("policy_id"))
            and max_compute > 0
            and tranche_total <= max_compute
            and tranche_policy.get("live_release_enabled") is False
            and all(isinstance(item, dict) and item.get("live_release_enabled") is False for item in tranches),
            {
                "intent_id": tranche_policy.get("intent_id"),
                "max_compute_budget_usdc": max_compute,
                "tranche_total_usdc": tranche_total,
                "live_release_enabled": tranche_policy.get("live_release_enabled"),
            },
            "compute tranche policy must cap spend and disable live releases",
        ),
        check(
            "near_1click_quote_request_is_dry_and_derived",
            quote_request.get("schema") == "auto-near-1click-quote-request/v1"
            and quote_request == expected_quote_request
            and quote_request.get("intent_id") == intent_id
            and quote_request.get("compute_tranche_policy_id") == tranche_policy.get("policy_id")
            and quote_request.get("dry") is True
            and quote_request.get("spendful") is False
            and quote_request.get("live_near_transaction") is False
            and quote_body.get("dry") is True
            and quote_body.get("swapType") in SUPPORTED_SWAP_TYPES
            and quote_body.get("depositType") in SUPPORTED_DEPOSIT_TYPES
            and quote_body.get("recipientType") in SUPPORTED_RECIPIENT_TYPES
            and quote_body.get("refundType") in SUPPORTED_REFUND_TYPES
            and quote_body.get("depositMode") in SUPPORTED_DEPOSIT_MODES
            and quote_body.get("confidentiality") in SUPPORTED_CONFIDENTIALITY_MODES
            and bool(quote_body.get("originAsset"))
            and bool(quote_body.get("destinationAsset"))
            and bool(quote_body.get("amount")),
            {
                "intent_id": quote_request.get("intent_id"),
                "compute_tranche_policy_id": quote_request.get("compute_tranche_policy_id"),
                "dry": quote_request.get("dry"),
                "quote_dry": quote_body.get("dry"),
                "swapType": quote_body.get("swapType"),
                "depositType": quote_body.get("depositType"),
                "depositMode": quote_body.get("depositMode"),
                "recipientType": quote_body.get("recipientType"),
                "refundType": quote_body.get("refundType"),
                "endpoint": quote_request.get("endpoint"),
            },
            "near-quote-request.json must be a derived 1Click dry quote request with no spend/live transaction",
        ),
        check(
            "near_1click_quote_enums_cover_current_docs",
            {"FLEX_INPUT", "ANY_INPUT"}.issubset(SUPPORTED_SWAP_TYPES)
            and "CONFIDENTIAL_INTENTS" in SUPPORTED_DEPOSIT_TYPES
            and "CONFIDENTIAL_INTENTS" in SUPPORTED_RECIPIENT_TYPES
            and "CONFIDENTIAL_INTENTS" in SUPPORTED_REFUND_TYPES
            and {"SIMPLE", "MEMO"}.issubset(SUPPORTED_DEPOSIT_MODES),
            {
                "supported_swap_types": sorted(SUPPORTED_SWAP_TYPES),
                "supported_deposit_types": sorted(SUPPORTED_DEPOSIT_TYPES),
                "supported_recipient_types": sorted(SUPPORTED_RECIPIENT_TYPES),
                "supported_refund_types": sorted(SUPPORTED_REFUND_TYPES),
                "supported_deposit_modes": sorted(SUPPORTED_DEPOSIT_MODES),
            },
            "1Click quote model must cover current documented enums including FLEX_INPUT, ANY_INPUT, CONFIDENTIAL_INTENTS, and depositMode",
        ),
        check(
            "mock_status_refund_receipt_is_dry_policy_not_real_swap",
            status_refund_receipt.get("schema") == "auto-near-1click-status-refund-receipt/v1"
            and status_refund_receipt == expected_status_refund_receipt
            and status_refund_receipt.get("intent_id") == intent_id
            and status_refund_receipt.get("settlement_id") == settlement_id
            and status_refund_receipt.get("mode") == "mock"
            and status_refund_receipt.get("spendful") is False
            and status_refund_receipt.get("live_near_transaction") is False
            and status_refund_receipt.get("status_endpoint_called") is False
            and status_refund_receipt.get("deposit_submitted") is False
            and status_refund_receipt.get("depositAddress") is None
            and status_refund_receipt.get("depositMemo") is None
            and status_refund_receipt.get("status") == DRY_STATUS_POLICY
            and status_refund_receipt.get("near_status") is None
            and "refundedAmount" not in refund
            and refund.get("refundTo") == quote_body.get("refundTo")
            and refund.get("refundType") == quote_body.get("refundType")
            and refund.get("policy_status") == "mock_refundable_if_proof_fails"
            and refund.get("actualRefundedAmount") is None,
            {
                "intent_id": status_refund_receipt.get("intent_id"),
                "settlement_id": status_refund_receipt.get("settlement_id"),
                "status": status_refund_receipt.get("status"),
                "near_status": status_refund_receipt.get("near_status"),
                "status_endpoint_called": status_refund_receipt.get("status_endpoint_called"),
                "deposit_submitted": status_refund_receipt.get("deposit_submitted"),
                "refund": refund,
            },
            "mock status/refund receipt must model dry refund policy without claiming a real NEAR status or refund",
        ),
        check(
            "mock_near_settlement_no_live_transaction",
            settlement.get("schema") == "auto-near-mock-settlement/v1"
            and settlement.get("intent_id") == intent_id
            and settlement.get("quote_request_id") == quote_request.get("quote_request_id")
            and settlement.get("mode") == "mock"
            and settlement.get("spendful") is False
            and settlement.get("live_near_transaction") is False
            and settlement.get("near_transaction_hash") is None,
            {
                "settlement_id": settlement_id,
                "mode": settlement.get("mode"),
                "spendful": settlement.get("spendful"),
                "live_near_transaction": settlement.get("live_near_transaction"),
                "near_transaction_hash": settlement.get("near_transaction_hash"),
            },
            "mock settlement must not submit or represent a live NEAR transaction",
        ),
        check(
            "settlement_links_to_proof_ledger_row",
            proof_link.get("schema") == "auto-intent-proof-link/v1"
            and proof_link.get("intent_id") == intent_id
            and proof_link.get("settlement_id") == settlement_id
            and proof_link.get("quote_request_id") == quote_request.get("quote_request_id")
            and proof_link.get("status_refund_receipt_id") == status_refund_receipt.get("status_refund_receipt_id")
            and proof_link.get("proof_ledger_row_id") == proof_row_id
            and proof_link.get("run_id") == proof_run_id
            and proof_link.get("artifact_sha256") == artifact_hash,
            {
                "intent_id": proof_link.get("intent_id"),
                "settlement_id": proof_link.get("settlement_id"),
                "proof_ledger_row_id": proof_link.get("proof_ledger_row_id"),
                "run_id": proof_link.get("run_id"),
            },
            "intent-proof-link.json must bind settlement to the AUTO proof ledger row",
        ),
        check(
            "auto_proof_ledger_row_is_no_spend_and_public_safe",
            not validate_proof_ledger_row(proof_ledger_row),
            {
                "proof_ledger_row_id": proof_row_id,
                "run_id": proof_run_id,
                "artifact_sha256": artifact_hash,
                "cost": proof_ledger_row.get("cost", {}),
                "source": proof_ledger_row.get("source", {}),
            },
            "proof-ledger-row.json must be a public-safe no-spend AUTO proof ledger row",
        ),
        check(
            "dashboard_has_settlement_refund_confidentiality_proof_status",
            dashboard.get("schema") == "auto-near-intents-public-dashboard/v1"
            and {"settlement", "refund", "confidentiality", "proof_status"}.issubset(dashboard_sections),
            {"dashboard_sections": sorted(dashboard_sections)},
            "public dashboard must expose settlement, refund, confidentiality, and proof status",
        ),
        check(
            "public_export_has_no_private_intent_leaks",
            export_policy.get("schema") == "auto-public-export-policy/v1"
            and PRIVATE_FIELD_NAMES.issubset(denied_field_names)
            and not leaked_values
            and not public_export_keys,
            {
                "denied_field_count": len(denied_field_names),
                "leaked_values": leaked_values,
                "public_private_field_keys": public_export_keys,
            },
            "public proof/dashboard exports must not leak private intent fields or values",
        ),
        check(
            "public_export_has_no_route_metadata_leaks",
            ROUTE_FIELD_NAMES.issubset(denied_field_names)
            and not public_route_keys
            and not leaked_route_values,
            {
                "denied_route_field_count": len(ROUTE_FIELD_NAMES & denied_field_names),
                "public_route_field_keys": public_route_keys,
                "leaked_route_values": leaked_route_values,
            },
            "public proof/dashboard exports must not expose recipient, refund, deposit, or settlement route metadata",
        ),
        check(
            "schemas_validate_artifacts",
            schema_validation.get("ok") is True,
            {
                "artifact_count": schema_validation.get("artifact_count"),
                "issues": schema_validation.get("issues", []),
            },
            "example artifacts must validate against their JSON schemas",
        ),
        check(
            "final_payout_blocked_until_proof_verified",
            settlement.get("final_payout", {}).get("status") == "blocked_until_proof_verified"
            and settlement.get("final_payout", {}).get("live_release_enabled") is False
            and proof_link.get("proof_verification", {}).get("status") == "pending_mock_verification",
            {
                "final_payout": settlement.get("final_payout", {}),
                "proof_verification": proof_link.get("proof_verification", {}),
            },
            "final payout must stay blocked until proof verification passes",
        ),
    ]
    passed = [item for item in checks if item["passed"]]
    failed = [item for item in checks if not item["passed"]]
    return {
        "schema": "auto-near-intents-demo-verification/v1",
        "ok": not failed,
        "spendful": False,
        "live_near_transaction": False,
        "root": str(root),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "checks": checks,
        "summary": {
            "intent_id": intent_id,
            "settlement_id": settlement_id,
            "quote_request_id": quote_request.get("quote_request_id"),
            "status_refund_receipt_id": status_refund_receipt.get("status_refund_receipt_id"),
            "proof_ledger_row_id": proof_row_id,
            "dashboard_section": "near_confidential_research_intent",
            "public_export_redacted": not leaked_values and not public_export_keys and not public_route_keys and not leaked_route_values,
            "no_live_spend": True,
        },
    }


def iter_publication_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in PUBLICATION_AUDIT_SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in PUBLICATION_AUDIT_SKIP_SUFFIXES:
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def audit_publication(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    issues: list[dict[str, Any]] = []
    checked_files = iter_publication_files(root)
    for path in checked_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative_path = str(path.relative_to(root))
        for name, pattern in PUBLICATION_RISK_PATTERNS.items():
            if pattern.search(text):
                issues.append(
                    {
                        "scope": "public_repo_scan",
                        "pattern": name,
                        "path": relative_path,
                        "issue": "publication-risk pattern found",
                    }
                )
    return {
        "schema": "auto-near-intents-publication-audit/v1",
        "ok": not issues,
        "spendful": False,
        "live_near_transaction": False,
        "root": str(root),
        "checked_file_count": len(checked_files),
        "issues": issues,
        "rule": (
            "Public repo artifacts must not contain real keys, private-key blocks, local AUTO internal paths, "
            "real cloud private dataset URIs, or private auto-token data paths."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the AUTO NEAR confidential research intent demo.")
    subparsers = parser.add_subparsers(dest="command")
    build = subparsers.add_parser("build-phase1", help="write Phase 1 1Click dry quote/status artifacts")
    build.add_argument("root", nargs="?", default="examples", type=Path)
    ingest = subparsers.add_parser("ingest-proof-ledger-row", help="ingest an AUTO proof-ledger row into the dry NEAR package")
    ingest.add_argument("proof_row", type=Path)
    ingest.add_argument("root", nargs="?", default="examples", type=Path)
    verify = subparsers.add_parser("verify", help="verify demo artifacts")
    verify.add_argument("root", nargs="?", default="examples", type=Path)
    audit = subparsers.add_parser("audit-publication", help="scan repo for public-publication risk patterns")
    audit.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    if args.command == "build-phase1":
        try:
            payload = build_phase1_artifacts(args.root)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "ingest-proof-ledger-row":
        try:
            payload = ingest_proof_ledger_row(args.root, args.proof_row)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        try:
            payload = verify_demo(args.root)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    if args.command == "audit-publication":
        payload = audit_publication(args.root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    else:
        parser.print_help()
        return 2
