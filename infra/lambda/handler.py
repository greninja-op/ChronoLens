"""AWS Lambda entry point — one ChronoLens loop tick on a schedule.

EventBridge invokes this every couple of minutes. It runs the managed loop
against SigNoz and mirrors each new case file into DynamoDB. Everything is
pay-per-use: Lambda + on-demand DynamoDB + (optional) Bedrock.

This is a scaffold. The ChronoLens package is expected to be layered in (or
vendored under ``lambda/chronolens``); the handler degrades gracefully with a
clear message if it isn't present yet.
"""
from __future__ import annotations

import json
import os


def _mirror_to_dynamo(cases: list[dict]) -> int:
    table_name = os.getenv("INCIDENTS_TABLE")
    if not table_name or not cases:
        return 0
    import boto3

    table = boto3.resource("dynamodb").Table(table_name)
    with table.batch_writer() as batch:
        for c in cases:
            batch.put_item(Item=json.loads(json.dumps(c), parse_float=str))
    return len(cases)


def run(event, context):  # noqa: ANN001 - Lambda signature
    try:
        from chronolens.config import Config
        from chronolens.loop import run_loop
        from chronolens.record import Ledger
        from chronolens.signoz import SigNozClient
    except Exception as exc:  # package not layered in yet
        return {"statusCode": 501,
                "body": json.dumps({"error": f"chronolens package unavailable: {exc}"})}

    cfg = Config.load()
    ledger = Ledger(root="/tmp/ledger")  # Lambda's writable scratch space
    before = ledger.total_count()
    try:
        with SigNozClient(cfg) as sn:
            result = run_loop(sn, cfg, managed=True, ledger=ledger)
    except Exception as exc:
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}

    new_cases = ledger.list()[before:]
    mirrored = _mirror_to_dynamo(new_cases)
    return {
        "statusCode": 200,
        "body": json.dumps({"outcome": result.get("outcome"),
                            "new_cases": len(new_cases), "mirrored": mirrored}),
    }
