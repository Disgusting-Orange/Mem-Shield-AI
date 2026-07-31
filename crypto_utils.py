"""
crypto_utils.py
----------------
Cryptographic helper functions for password hashing, salt generation,
emergency recovery key generation, and payload security.

Used by vault_store.py to ensure zero-knowledge password verification.
"""

import os
import hashlib
import secrets
import string
from typing import Tuple


def generate_salt() -> str:
    """Generate a random 16-byte hex salt."""
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    )
    return key.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify a raw password against its salt and expected hash."""
    computed = hash_password(password, salt)
    return secrets.compare_digest(computed, expected_hash)


def generate_recovery_key() -> str:
    """Generate a 16-character Emergency Recovery Key in format: MEM-XXXX-XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    # Exclude ambiguous characters like 0, O, 1, I
    chars = "".join([c for c in chars if c not in "0OI1"])
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    part3 = "".join(secrets.choice(chars) for _ in range(4))
    return f"MEM-{part1}-{part2}-{part3}"


def hash_recovery_key(recovery_key: str) -> str:
    """Hash the recovery key for secure storage."""
    clean_key = recovery_key.strip().upper().replace(" ", "").replace("-", "")
    return hashlib.sha256(clean_key.encode("utf-8")).hexdigest()


def verify_recovery_key(input_key: str, expected_hash: str) -> bool:
    """Verify a user-provided recovery key against stored hash."""
    computed = hash_recovery_key(input_key)
    return secrets.compare_digest(computed, expected_hash)
