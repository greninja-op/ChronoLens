#!/usr/bin/env bash
# Vendor the chronolens package into the Lambda source dir so `sam build` packages
# it alongside the handler. Run before `sam build && sam deploy`.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HERE/src/chronolens"
DST="$HERE/infra/lambda/chronolens"

echo "==> vendoring chronolens -> infra/lambda/chronolens"
rm -rf "$DST"
mkdir -p "$DST"
# copy the package, skipping caches
( cd "$SRC" && tar --exclude='__pycache__' -cf - . ) | ( cd "$DST" && tar -xf - )

echo "done. Now:"
echo "  cd infra && sam build && sam deploy --guided \\"
echo "    --parameter-overrides SigNozUrl=https://signoz.example.com"
echo "  (put the API key in SSM first:  aws ssm put-parameter \\"
echo "     --name /chronolens/signoz-api-key --type SecureString --value <key>)"
