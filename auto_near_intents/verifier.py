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
    "settlement": "mock-near-settlement.json",
    "proof_ledger_row": "proof-ledger-row.json",
    "proof_link": "intent-proof-link.json",
    "dashboard": "public-dashboard.json",
    "redacted_proof": "public-redacted-proof.json",
    "export_policy": "public-export-policy.json",
}

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


def verify_demo(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    demo = load_demo(root)
    intent = demo["intent"]
    tranche_policy = demo["tranche_policy"]
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

    public_values = [dashboard, redacted_proof]
    private_values = find_values(intent, PRIVATE_VALUE_FIELDS)
    public_export_keys = sorted(set(find_keys(public_values, PRIVATE_FIELD_NAMES)))
    leaked_values = sorted(
        value
        for value in private_values
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
            "mock_near_settlement_no_live_transaction",
            settlement.get("schema") == "auto-near-mock-settlement/v1"
            and settlement.get("intent_id") == intent_id
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
            "proof_ledger_row_id": proof_row_id,
            "dashboard_section": "near_confidential_research_intent",
            "public_export_redacted": not leaked_values and not public_export_keys,
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
    verify = subparsers.add_parser("verify", help="verify demo artifacts")
    verify.add_argument("root", nargs="?", default="examples", type=Path)
    audit = subparsers.add_parser("audit-publication", help="scan repo for public-publication risk patterns")
    audit.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
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
