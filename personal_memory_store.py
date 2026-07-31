"""
personal_memory_store.py
-------------------------
Database for storing firewall-inspected personal data, medical records, and user preferences.

All entries must pass through the Memory Firewall first before being saved here.
"""

import sqlite3
import time
from typing import List, Dict, Optional


class PersonalMemoryStore:
    """Store for safe user personal & medical memories."""

    def __init__(self, db_path: str = "personal_memory.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS personal_memories (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT,
                category TEXT,
                title TEXT,
                content TEXT,
                threat_score INTEGER,
                reasons_json TEXT,
                created_at REAL
            )
        """)
        self.conn.commit()

    def save_memory(
        self,
        memory_id: str,
        user_id: str,
        category: str,
        title: str,
        content: str,
        threat_score: int,
        reasons: List[str]
    ) -> Dict:
        import json
        now = time.time()
        reasons_json = json.dumps(reasons)

        self.conn.execute(
            """
            INSERT OR REPLACE INTO personal_memories
            (memory_id, user_id, category, title, content, threat_score, reasons_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (memory_id, user_id, category, title, content, threat_score, reasons_json, now)
        )
        self.conn.commit()

        return {
            "memory_id": memory_id,
            "user_id": user_id,
            "category": category,
            "title": title,
            "content": content,
            "threat_score": threat_score,
            "reasons": reasons,
            "created_at": now,
        }

    def list_memories(self, user_id: str, category: Optional[str] = None) -> List[Dict]:
        import json
        if category:
            cursor = self.conn.execute(
                "SELECT memory_id, category, title, content, threat_score, reasons_json, created_at FROM personal_memories WHERE user_id = ? AND category = ? ORDER BY created_at DESC",
                (user_id, category)
            )
        else:
            cursor = self.conn.execute(
                "SELECT memory_id, category, title, content, threat_score, reasons_json, created_at FROM personal_memories WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )

        memories = []
        for row in cursor.fetchall():
            try:
                reasons = json.loads(row[5]) if row[5] else []
            except (json.JSONDecodeError, TypeError):
                reasons = []

            memories.append({
                "memory_id": row[0],
                "category": row[1],
                "title": row[2],
                "content": row[3],
                "threat_score": row[4],
                "reasons": reasons,
                "created_at": row[6],
            })
        return memories
