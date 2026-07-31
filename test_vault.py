"""
test_vault.py
--------------
Automated test suite verifying:
1. Automatic AI Medical classification & auto-vaulting heuristics.
2. Medical and personal record upload, firewall interception, and retrieval.
3. Isolated database creation in `private_vault.db`.
4. Private chat locking with PBKDF2 password hashing & salt generation.
5. Correct password decryption & wrong password rejection.
6. Emergency Recovery Key generation & password reset functionality.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from vault_store import VaultStore
from personal_memory_store import PersonalMemoryStore
from memory_firewall.firewall import MemoryFirewall
from crypto_utils import generate_salt, hash_password, verify_password, generate_recovery_key, verify_recovery_key


class TestVaultAndMemory(unittest.TestCase):

    def setUp(self):
        self.test_vault_db = "test_private_vault.db"
        self.test_personal_db = "test_personal_memory.db"
        self.vault = VaultStore(self.test_vault_db)
        self.personal_store = PersonalMemoryStore(self.test_personal_db)
        self.firewall = MemoryFirewall()

    def tearDown(self):
        self.vault.conn.close()
        self.personal_store.conn.close()
        if os.path.exists(self.test_vault_db):
            os.remove(self.test_vault_db)
        if os.path.exists(self.test_personal_db):
            os.remove(self.test_personal_db)

    def test_automatic_medical_classifier(self):
        medical_text = "Patient reports high fever of 101F, blood test shows elevated WBC, prescribed Paracetamol 500mg."
        res = self.firewall.classify_content(medical_text)
        self.assertTrue(res["is_medical"])
        self.assertEqual(res["category"], "medical")

        general_text = "What is the capital of France and what are the best tourist places to visit?"
        res2 = self.firewall.classify_content(general_text)
        self.assertFalse(res2["is_medical"])
        self.assertEqual(res2["category"], "general")

    def test_crypto_hashing_and_verification(self):
        salt = generate_salt()
        pwd = "SecretPassword123!"
        hashed = hash_password(pwd, salt)

        self.assertTrue(verify_password(pwd, salt, hashed))
        self.assertFalse(verify_password("WrongPassword!", salt, hashed))

    def test_recovery_key_format_and_verification(self):
        rec_key = generate_recovery_key()
        self.assertTrue(rec_key.startswith("MEM-"))
        self.assertEqual(len(rec_key), 18)

        from crypto_utils import hash_recovery_key
        key_hash = hash_recovery_key(rec_key)
        self.assertTrue(verify_recovery_key(rec_key, key_hash))
        self.assertFalse(verify_recovery_key("MEM-0000-0000-0000", key_hash))

    def test_vault_create_and_unlock_chat(self):
        chat_id = "chat_test_01"
        user_id = "user_test"
        pwd = "MyVaultPassword"

        summary, recovery_key = self.vault.create_chat(
            chat_id=chat_id,
            user_id=user_id,
            title="Confidential Medical Inquiry",
            initial_messages=[{"sender": "user", "text": "Patient has penicillin allergy."}],
            password=pwd
        )

        self.assertTrue(summary["is_locked"])
        self.assertIsNotNone(recovery_key)

        success, msgs, msg = self.vault.unlock_chat(chat_id, "WrongPassword")
        self.assertFalse(success)
        self.assertIsNone(msgs)

        success, msgs, msg = self.vault.unlock_chat(chat_id, pwd)
        self.assertTrue(success)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "Patient has penicillin allergy.")

    def test_password_reset_with_recovery_key(self):
        chat_id = "chat_reset_test"
        pwd = "OriginalPassword"

        _, recovery_key = self.vault.create_chat(
            chat_id=chat_id,
            user_id="user_test",
            title="Locked Chat Reset Test",
            password=pwd
        )

        reset_ok, msg = self.vault.reset_password(chat_id, "MEM-9999-9999-9999", "NewPassword")
        self.assertFalse(reset_ok)

        reset_ok, msg = self.vault.reset_password(chat_id, recovery_key, "NewPassword123!")
        self.assertTrue(reset_ok)

        success, _, _ = self.vault.unlock_chat(chat_id, pwd)
        self.assertFalse(success)

        success, msgs, _ = self.vault.unlock_chat(chat_id, "NewPassword123!")
        self.assertTrue(success)

    def test_personal_memory_save_and_retrieve(self):
        mem = self.personal_store.save_memory(
            memory_id="mem_01",
            user_id="user_test",
            category="medical",
            title="Blood Pressure Log",
            content="Systolic 120, Diastolic 80",
            threat_score=95,
            reasons=["Clean medical data"]
        )

        self.assertEqual(mem["title"], "Blood Pressure Log")

        memories = self.personal_store.list_memories("user_test", "medical")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["content"], "Systolic 120, Diastolic 80")


if __name__ == "__main__":
    unittest.main()
