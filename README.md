# AUTO NEAR Intents Plugin

Open-source reference plugin for proof-gated autonomous research intents using NEAR as the confidential settlement layer.

This is the public collaboration repo for a NEAR x AUTO integration. It shows how an external buyer can fund an autonomous research objective, cap compute tranches, link settlement to an AUTO proof ledger row, and publish only redacted proof.

The repo is intentionally offline-first. The demo uses a mock NEAR settlement receipt, proves compute tranches are capped, links settlement to an AUTO proof ledger row, and verifies that public proof exports do not leak confidential intent fields.

## Collaboration Thesis

```text
AUTO = research/proof operating system
NEAR Intents = confidential cross-chain settlement/refund rail
GitLawb/dashboard = public-safe proof publication
Bittensor = optional research miner incentive network
```

The integration path is: keep AUTO's proof and IP boundary, use NEAR Intents for settlement/refunds, and use Confidential Intents for private procurement details such as buyer identity, target topic, budget, timing, and settlement route.

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
python3 -m auto_near_intents audit-publication .
```

All commands are no-spend. They do not call NEAR, submit a transaction, sign a payload, or release funds. If `pytest` is installed, the same tests are also pytest-compatible.

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

## Live NEAR Plan

See [docs/live-near-integration-plan.md](docs/live-near-integration-plan.md). The next implementation should start with 1Click quote/status integration in dry mode, then add Verifier contract simulation, and only then enable a tiny mainnet live path behind explicit approval. The NEAR Intents Verifier contract currently has no testnet deployment, so this repo treats all live movement as gated future work.
