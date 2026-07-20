# ChronoLens on AWS (serverless scaffold)

This runs the ChronoLens loop **without a server** — a scheduled Lambda pulls
SigNoz, forecasts, prevents, verifies, and records to DynamoDB. Everything is
pay-per-use, which fits the hackathon's serverless / ~$100 budget rule.

```
EventBridge (rate 2m)  ──►  Lambda: run_loop(managed=True)  ──►  SigNoz (read + alert/dashboard writes)
                                     │
                                     └──►  DynamoDB (incident ledger, on-demand)
                                     └──►  Bedrock (optional NL explanations)
```

## What's here
- `template.yaml` — AWS SAM template (Lambda + EventBridge schedule + on-demand DynamoDB + Bedrock IAM).
- `lambda/handler.py` — the Lambda entry point; runs one loop tick and mirrors new cases into DynamoDB.

## This is a scaffold
It deploys the **shape** of the system. Two things to wire before it does real work:

1. **Layer in the package.** Vendor `src/chronolens` into `lambda/chronolens/`
   (plus `httpx`, `opentelemetry-*`) or attach them as a Lambda layer.
2. **Real SigNoz creds.** Pass `SigNozUrl` / `SigNozApiKey` at deploy time —
   prefer an SSM SecureString or Secrets Manager over a plain parameter.

## Deploy (once creds + package are in place)
```bash
sam build
sam deploy --guided \
  --parameter-overrides SigNozUrl=https://signoz.example.com SigNozApiKey=... LlmProvider=bedrock
```

## Notes
- `CHRONOLENS_AUTONOMY=earn` is set in prod, so the loop only acts autonomously
  after it has proven itself with verified saves (the trust ladder).
- DynamoDB is `PAY_PER_REQUEST` — you pay per write, nothing when idle.
- Not deployed as part of the hackathon demo (no live AWS account wired); the
  local `casting.yaml` bring-up is the primary path. This scaffold shows the
  serverless production shape.
