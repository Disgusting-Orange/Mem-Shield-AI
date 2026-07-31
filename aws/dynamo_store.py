"""
aws/dynamo_store.py
--------------------
DynamoDB-backed StateStore for execution steps.
Drop-in replacement for the local SQLite StateStore.

Table: mem-shield-steps
  PK: agent_id (S)
  SK: timestamp (N)
"""

import json
import time
import logging
from typing import List

import boto3
from boto3.dynamodb.conditions import Key

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models import ExecutionStep
from interfaces import BaseStateStore

logger = logging.getLogger(__name__)

TABLE_NAME = os.environ.get("DYNAMO_STEPS_TABLE", "mem-shield-steps")


class DynamoStateStore(BaseStateStore):
    """Persists execution steps to DynamoDB (free tier: 25 GB, 25 RCU/WCU)."""

    def __init__(self, table_name: str = TABLE_NAME):
        self._dynamo = boto3.resource("dynamodb")
        self._table = self._dynamo.Table(table_name)
        logger.info("DynamoStateStore connected to table: %s", table_name)

    def save(self, step: ExecutionStep) -> None:
        self._table.put_item(Item={
            "agent_id": step.agent_id,
            "timestamp": str(step.timestamp),  # DynamoDB Number via string
            "step_id": step.step_id,
            "action": step.action,
            "params": json.dumps(step.params),
            "status": step.status,
            "cost_estimate": str(step.cost_estimate),
            "result_payload": step.result_payload or "",
        })

    def get_steps(self, agent_id: str) -> List[ExecutionStep]:
        response = self._table.query(
            KeyConditionExpression=Key("agent_id").eq(agent_id),
            ScanIndexForward=True,  # ascending by sort key (timestamp)
        )
        steps = []
        for item in response.get("Items", []):
            try:
                params = json.loads(item.get("params", "{}"))
            except (json.JSONDecodeError, TypeError):
                params = {}
            steps.append(ExecutionStep(
                agent_id=item["agent_id"],
                step_id=item.get("step_id", ""),
                action=item.get("action", ""),
                params=params,
                status=item.get("status", "pending"),
                timestamp=float(item.get("timestamp", 0)),
                cost_estimate=float(item.get("cost_estimate", 0)),
                result_payload=item.get("result_payload"),
            ))
        return steps
