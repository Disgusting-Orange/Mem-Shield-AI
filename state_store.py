"""
state_store.py
---------------
Free local replacement for DynamoDB. Same job: durable step log.
Swapping to DynamoDB later means only changing this file's internals --
guardian.py never talks to AWS directly.
"""

import sqlite3
from models import ExecutionStep


class StateStore:
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

    def save(self, step: ExecutionStep):
        self.conn.execute(
            "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step.agent_id, step.step_id, step.action, str(step.params),
             step.status, step.timestamp, step.cost_estimate, step.result_payload)
        )
        self.conn.commit()
