# Publication Safety

This repo is designed to be public.

The example private fields are synthetic fixtures. They exist so the verifier can prove that public dashboard/proof exports do not leak private intent values.

Before publishing or updating the public repo, run:

```sh
python3 -m unittest discover -s tests
python3 -m auto_near_intents verify examples
python3 -m auto_near_intents audit-publication .
git diff --check HEAD
```

The publication audit scans for:

- GitHub-style access tokens
- OpenAI-style API keys
- private-key blocks
- private key environment assignments
- Venice API key environment variables
- local `auto-token` paths
- private `auto-token/data` paths
- real cloud private dataset URIs using the S3 scheme

The public export verifier separately checks that the public dashboard and public redacted proof do not include private intent field names or values.
