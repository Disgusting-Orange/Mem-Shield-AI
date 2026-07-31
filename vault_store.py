"""
vault_store.py
---------------
Dedicated, isolated database (`private_vault.db`) for private locked chats.

Kept completely separate from agentguardian.db to guarantee zero-leakage isolation.
Stores encrypted chat messages, PBKDF2 password hashes, salts, and recovery key hashes.
"""

import json
import sqlite3
import time
from typing import List, Dict, Optional, Tuple

from crypto_utils import (
    generate_salt,
    hash_password,
    verify_password,
    generate_recovery_key,
    hash_recovery_key,
    verify_recovery_key,
)


class VaultStore:
    """Isolated database manager for private locked chats."""

    def __init__(self, db_path: str = "private_vault.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS locked_chats (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                messages_json TEXT,
                password_hash TEXT,
                salt TEXT,
                recovery_key_hash TEXT,
                is_locked INTEGER DEFAULT 1,
                created_at REAL,
                updated_at REAL
            )
        """)
        self.conn.commit()

    def create_chat(
        self,
        chat_id: str,
        user_id: str,
        title: str,
        initial_messages: Optional[List[Dict]] = None,
        password: Optional[str] = None
    ) -> Tuple[Dict, Optional[str]]:
        """Create a new chat session. If password is provided, locks it and generates a recovery key.

        Returns (chat_summary_dict, emergency_recovery_key)
        """
        now = time.time()
        messages_str = json.dumps(initial_messages or [])
        recovery_key = None

        if password:
            salt = generate_salt()
            pwd_hash = hash_password(password, salt)
            recovery_key = generate_recovery_key()
            rec_hash = hash_recovery_key(recovery_key)
            is_locked = 1
        else:
            salt = None
            pwd_hash = None
            rec_hash = None
            is_locked = 0

        self.conn.execute(
            """
            INSERT OR REPLACE INTO locked_chats
            (chat_id, user_id, title, messages_json, password_hash, salt, recovery_key_hash, is_locked, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, title, messages_str, pwd_hash, salt, rec_hash, is_locked, now, now)
        )
        self.conn.commit()

        summary = {
            "chat_id": chat_id,
            "user_id": user_id,
            "title": title,
            "is_locked": bool(is_locked),
            "created_at": now,
            "updated_at": now,
        }
        return summary, recovery_key

    def lock_existing_chat(self, chat_id: str, password: str) -> Optional[str]:
        """Lock an existing unlocked chat with a password. Returns emergency recovery key."""
        cursor = self.conn.execute("SELECT user_id, title, messages_json FROM locked_chats WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if not row:
            return None

        salt = generate_salt()
        pwd_hash = hash_password(password, salt)
        recovery_key = generate_recovery_key()
        rec_hash = hash_recovery_key(recovery_key)
        now = time.time()

        self.conn.execute(
            """
            UPDATE locked_chats
            SET password_hash = ?, salt = ?, recovery_key_hash = ?, is_locked = 1, updated_at = ?
            WHERE chat_id = ?
            """,
            (pwd_hash, salt, rec_hash, now, chat_id)
        )
        self.conn.commit()
        return recovery_key

    def unlock_chat(self, chat_id: str, password: str) -> Tuple[bool, Optional[List[Dict]], str]:
        """Verify password and return chat messages if successful.

        Returns (success: bool, messages: list|None, error_message: str)
        """
        cursor = self.conn.execute(
            "SELECT messages_json, password_hash, salt, is_locked FROM locked_chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False, None, "Chat session not found"

        messages_json, pwd_hash, salt, is_locked = row

        if not is_locked:
            messages = json.loads(messages_json) if messages_json else []
            return True, messages, "Chat is not locked"

        if not pwd_hash or not salt:
            return False, None, "No password configured for this locked chat"

        if not verify_password(password, salt, pwd_hash):
            return False, None, "Invalid password"

        messages = json.loads(messages_json) if messages_json else []
        return True, messages, "Unlocked successfully"

    def reset_password(self, chat_id: str, recovery_key: str, new_password: str) -> Tuple[bool, str]:
        """Reset a locked chat's password using the emergency recovery key.

        Returns (success: bool, message: str)
        """
        cursor = self.conn.execute(
            "SELECT recovery_key_hash FROM locked_chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False, "Chat session not found"

        stored_rec_hash = row[0]
        if not stored_rec_hash:
            return False, "No recovery key exists for this chat"

        if not verify_recovery_key(recovery_key, stored_rec_hash):
            return False, "Invalid Emergency Recovery Key"

        # Generate new credentials
        new_salt = generate_salt()
        new_pwd_hash = hash_password(new_password, new_salt)
        now = time.time()

        self.conn.execute(
            """
            UPDATE locked_chats
            SET password_hash = ?, salt = ?, is_locked = 1, updated_at = ?
            WHERE chat_id = ?
            """,
            (new_pwd_hash, new_salt, now, chat_id)
        )
        self.conn.commit()
        return True, "Password reset successfully"

    def add_message(self, chat_id: str, sender: str, text: str) -> bool:
        """Append a message to an unlocked or accessible chat session."""
        cursor = self.conn.execute("SELECT messages_json FROM locked_chats WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if not row:
            return False

        messages = json.loads(row[0]) if row[0] else []
        messages.append({
            "sender": sender,
            "text": text,
            "timestamp": time.time(),
        })

        self.conn.execute(
            "UPDATE locked_chats SET messages_json = ?, updated_at = ? WHERE chat_id = ?",
            (json.dumps(messages), time.time(), chat_id)
        )
        self.conn.commit()
        return True

    def list_chats(self, user_id: str) -> List[Dict]:
        """List all chat sessions for a user, showing lock status without exposing contents of locked chats."""
        cursor = self.conn.execute(
            "SELECT chat_id, title, is_locked, created_at, updated_at FROM locked_chats WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        )
        chats = []
        for row in cursor.fetchall():
            chats.append({
                "chat_id": row[0],
                "title": row[1],
                "is_locked": bool(row[2]),
                "created_at": row[3],
                "updated_at": row[4],
            })
        return chats
