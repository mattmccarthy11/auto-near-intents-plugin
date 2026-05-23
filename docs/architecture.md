# AUTO x NEAR Confidential Research Intent Plugin

This plugin demonstrates the interface between AUTO proof-ledger artifacts and NEAR-style settlement evidence.

## Boundary

AUTO owns:

- research task/proof semantics
- proof ledger row identity
- artifact hashes
- proof verification status
- public/private export policy

NEAR owns:

- cross-chain settlement route
- escrow/refund state
- confidential settlement account flow
- eventual live transaction receipts

This demo does not execute a live transaction. It creates a mock settlement receipt that has the same proof-linking shape the live adapter should produce later.

## Flow

```text
research-intent.json
  -> compute-tranche-policy.json
  -> near-quote-request.json
  -> mock-near-status-refund-receipt.json
  -> mock-near-settlement.json
  -> proof-ledger-row.json
  -> intent-proof-link.json
  -> public-dashboard.json
  -> public-redacted-proof.json
```

## Rule

Compute can be budgeted upfront, but final settlement is proof-gated. The public proof can show settlement state, refund state, proof status, and hashes. It must not reveal the buyer's private subject, confidential prompt, private dataset URI, internal buyer ID, exact confidential budget, or private settlement memo.
