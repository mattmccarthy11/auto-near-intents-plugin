# Live NEAR Integration Plan

This document turns the current mock plugin into a live NEAR integration without weakening AUTO's proof, budget, and IP boundaries.

## Current State

The repo is a no-spend demo. It creates a confidential research intent, a capped compute tranche policy, a mock NEAR settlement receipt, a proof-ledger link, and public redacted proof. The verifier proves that final payout is blocked until proof verification and that the public export does not leak private intent fields.

## NEAR Surface

The first live adapter should prefer the 1Click Swap API because it handles intent creation, market maker coordination, execution, status tracking, retries, and refund handling for common applications. Direct Verifier contract integration is phase two because it requires lower-level payload construction, signatures, deposits, and withdrawals.

Current NEAR facts the adapter must respect:

- The Verifier contract is the on-chain settlement layer for NEAR Intents and is deployed at `intents.near`.
- The Verifier contract keeps an internal ledger of participant balances; external-chain movement happens on withdrawal.
- Most app integrations can start with 1Click instead of direct Verifier contract calls.
- The Verifier docs state that there is no testnet deployment, so live tests must use tiny mainnet amounts only after explicit approval.
- `simulate_intents` can test signed intent payloads without modifying Verifier state.
- Confidential Intents are designed for restricted visibility, selective disclosure, and auditable execution.

Sources:

- https://docs.near-intents.org/integration/distribution-channels/1click-api/about-1click-api
- https://docs.near-intents.org/integration/verifier-contract/introduction
- https://docs.near-intents.org/integration/verifier-contract/simulating-intents
- https://docs.near-intents.org/integration/verifier-contract/events
- https://intents.near.org/confidential

## Phases

### Phase 0: Current Mock Adapter

Status: complete in this repo.

Proof:

```sh
python3 -m unittest discover -s tests
python3 -m auto_near_intents verify examples
python3 -m auto_near_intents audit-publication .
```

### Phase 1: 1Click Dry Quote Adapter

Add a `near-quote-request.json` artifact that maps `research-intent.json` and `compute-tranche-policy.json` into a 1Click quote request with `dry: true`, plus `mock-near-status-refund-receipt.json` to represent the status/refund side without calling the API.

Required behavior:

- no deposit
- no signature
- no transaction hash
- no final payout release
- quote/status metadata linked back to `intent_id` and `proof_ledger_row_id`
- all private research fields excluded from public quote artifacts

### Phase 2: Verifier Simulation Adapter

Add a `near-simulated-intent.json` artifact for `simulate_intents`.

Required behavior:

- construct a signed-payload placeholder or fixture
- call simulation only in an explicitly enabled development mode
- record simulation result hashes, not private research details
- continue blocking final payout until AUTO proof verification passes

### Phase 3: Tiny Mainnet Settlement Gate

Because there is no testnet deployment, live mode must require all of the following:

- explicit operator approval file
- tiny max amount
- known refund address
- proof-ledger row already created
- public export audit passing
- confirmation that private fields are not in any public artifact
- final payout release disabled until proof verification passes

The first live transaction should only prove plumbing. It should not carry a real customer task, real confidential prompt, real private dataset URI, or real settlement memo.

### Phase 4: Confidential Account Flow

Map the same proof-gated flow onto Confidential Intents when the NEAR team confirms the production integration surface for private-shard or confidential-account execution.

The public artifacts should still reveal only:

- intent id
- settlement id
- proof ledger row id
- artifact hash
- refund status
- proof status
- redaction status

## Non-Goals

- This plugin does not replace AUTO's proof ledger.
- This plugin does not publish private research strategy.
- This plugin does not send funds by default.
- This plugin does not claim production readiness for live NEAR settlement.
