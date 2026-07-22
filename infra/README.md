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

## Deploy
```bash
# 1) store the SigNoz API key as an SSM SecureString (never in the template)
aws ssm put-parameter --name /chronolens/signoz-api-key --type SecureString --value <API_KEY>

# 2) vendor the chronolens package into the Lambda source dir
bash ../scripts/build-lambda.sh        # (or ../scripts/build-lambda.ps1 on Windows)

# 3) build + deploy (SAM installs lambda/requirements.txt into the package)
sam build
sam deploy --guided \
  --parameter-overrides SigNozUrl=https://signoz.example.com LlmProvider=bedrock
```
The template reads the key at deploy time via a dynamic reference
(`{{resolve:ssm-secure:/chronolens/signoz-api-key}}`), so the secret never lands
in CloudFormation or the repo.

> Not deployed as part of this hackathon (no live AWS account wired). The steps
> above are complete and standard SAM — the local `casting.yaml` + `docker compose`
> path is the primary demo; this is the pay-per-use production shape.

## Notes
- `CHRONOLENS_AUTONOMY=earn` is set in prod, so the loop only acts autonomously
  after it has proven itself with verified saves (the trust ladder).
- DynamoDB is `PAY_PER_REQUEST` — you pay per write, nothing when idle.
- Not deployed as part of the hackathon demo (no live AWS account wired); the
  local `casting.yaml` bring-up is the primary path. This scaffold shows the
  serverless production shape.
