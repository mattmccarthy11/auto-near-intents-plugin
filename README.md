# AUTO NEAR Intents Plugin

Open-source reference plugin for proof-gated autonomous research intents using NEAR as the settlement layer.

This repo is intentionally offline-first. The demo uses a mock NEAR settlement receipt, proves compute tranches are capped, links settlement to an AUTO proof ledger row, and verifies that public proof exports do not leak confidential intent fields.

## Demo Artifacts

```text
examples/research-intent.json
examples/compute-tranche-policy.json
examples/mock-near-settlement.json
examples/proof-ledger-row.json
examples/intent-proof-link.json
examples/public-dashboard.json
examples/public-redacted-proof.json
examples/public-export-policy.json
```

## Verify

```sh
python3 -m unittest discover -s tests
python3 -m auto_near_intents verify examples
```

Both commands are no-spend. They do not call NEAR, submit a transaction, sign a payload, or release funds. If `pytest` is installed, the same tests are also pytest-compatible.

## Architecture

```text
AUTO core proof loop
  -> research intent
  -> capped compute tranche policy
  -> mock NEAR settlement receipt
  -> AUTO proof ledger row
  -> public redacted proof/dashboard
```

The plugin boundary is deliberate:

```text
AUTO = research/proof operating system
NEAR Intents = confidential cross-chain settlement/refund rail
Bittensor = optional research miner incentive network
GitLawb/dashboard = public-safe proof publication
```

The public export rule is simple: publish IDs, hashes, statuses, and proof state; never publish private prompt, private dataset URI, internal buyer identity, exact confidential budget, or confidential settlement metadata.
