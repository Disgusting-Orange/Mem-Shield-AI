"""
aws/dynamo_history_store.py
----------------------------
DynamoDB-backed history store for the Memory Firewall's semantic drift
detection. Persists accepted writes so that restarting the Lambda container
does not lose drift history.

Table: mem-shield-write-history
  PK: agent_id (S)
  SK: write_ts  (N)
"""

import os
import time
import logging
from typing import List, Dict

import boto3
from boto3.dynamodb.conditions import Key

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from interfaces import BaseHistoryStore

logger = logging.getLogger(__name__)

TABLE_NAME = os.environ.get("DYNAMO_HISTORY_TABLE", "mem-shield-write-history")


class DynamoHistoryStore(BaseHistoryStore):
    """Persists firewall write history to DynamoDB (free tier)."""

    def __init__(self, table_name: str = TABLE_NAME):
        self._dynamo = boto3.resource("dynamodb")
        self._table = self._dynamo.Table(table_name)
        logger.info("DynamoHistoryStore connected to table: %s", table_name)

    def load_history(self, agent_id: str) -> List[Dict[str, str]]:
        response = self._table.query(
            KeyConditionExpression=Key("agent_id").eq(agent_id),
            ScanIndexForward=True,
        )
        return [
            {"key": item.get("key", ""), "value": item.get("value", "")}
            for item in response.get("Items", [])
        ]

    def append_write(self, agent_id: str, key: str, value: str) -> None:
        self._table.put_item(Item={
            "agent_id": agent_id,
            "write_ts": str(time.time()),
            "key": key,
            "value": value,
        })
