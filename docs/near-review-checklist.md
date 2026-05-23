# NEAR Review Checklist

This repo is a no-spend partner review package. It does not call NEAR, sign payloads, deposit funds, submit transaction hashes, or release payouts.

## What To Review

- Does `examples/near-quote-request.json` match the current 1Click quote request shape for a dry request?
- Are `depositType`, `depositMode`, `swapType`, `recipientType`, `refundType`, and `confidentiality` modeled correctly for a future Confidential Intents flow?
- Is `CONFIDENTIAL_INTENTS` the right route type for confidential recipient and refund accounts?
- Should the first live proof use 1Click only, direct Verifier simulation first, or both?
- Is the dry no-deposit status policy in `examples/mock-near-status-refund-receipt.json` the right way to avoid claiming a real 1Click status before a deposit address exists?
- Which fields from a real quote/status response are safe for public proof dashboards, and which must remain internal?
- What explicit approval and amount caps should be required before a tiny mainnet proof?

## Local Review Commands

```sh
python3 -m unittest discover -s tests
python3 -m auto_near_intents build-phase1 examples
python3 -m auto_near_intents verify examples
python3 -m auto_near_intents audit-publication .
git diff --check HEAD
```

`build-phase1` is deterministic and no-spend. The tests also run the builder against a temporary copy of `examples/` so tracked fixtures are not silently rewritten during normal test execution.

## Public Export Rule

Public artifacts may show IDs, hashes, proof state, redaction state, spend flags, live-transaction flags, and high-level settlement/refund policy status.

Public artifacts must not show private research text, private dataset URI, internal buyer identity, exact confidential budget, recipient route, refund route, deposit address, deposit memo, transaction hash, or confidential settlement memo.
