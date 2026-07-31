"""
state_store.py
---------------
Free local replacement for DynamoDB. Same job: durable step log.
Swapping to DynamoDB later means only changing this file's internals --
guardian.py never talks to AWS directly.
"""

import json
import sqlite3
from typing import List

from models import ExecutionStep
from interfaces import BaseStateStore


class StateStore(BaseStateStore):
    def __init__(self, db_path: str = "agentguardian.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS steps (
                agent_id TEXT,
                step_id TEXT,
                action TEXT,
                params TEXT,
                status TEXT,
                timestamp REAL,
                cost_estimate REAL,
                result_payload TEXT
            )
        """)
        self.conn.commit()

    def save(self, step: ExecutionStep) -> None:
        self.conn.execute(
            "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step.agent_id, step.step_id, step.action, json.dumps(step.params),
             step.status, step.timestamp, step.cost_estimate, step.result_payload)
        )
        self.conn.commit()

    def get_steps(self, agent_id: str) -> List[ExecutionStep]:
        cursor = self.conn.execute(
            "SELECT agent_id, step_id, action, params, status, timestamp, cost_estimate, result_payload "
            "FROM steps WHERE agent_id = ? ORDER BY timestamp",
            (agent_id,)
        )
        steps = []
        for row in cursor.fetchall():
            try:
                params = json.loads(row[3])
            except (json.JSONDecodeError, TypeError):
                params = {}
            steps.append(ExecutionStep(
                agent_id=row[0],
                step_id=row[1],
                action=row[2],
                params=params,
                status=row[4],
                timestamp=row[5],
                cost_estimate=row[6],
                result_payload=row[7],
            ))
        return steps
