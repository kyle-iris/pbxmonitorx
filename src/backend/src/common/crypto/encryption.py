"""AES-256-GCM encryption for PBX credentials.

Passwords are encrypted at rest and only decrypted in-memory when needed
for PBX authentication. The master key is provided via environment variable.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config.settings import get_settings


def encrypt_secret(plaintext: str) -> tuple[bytes, bytes, bytes]:
    """Encrypt a secret string using AES-256-GCM.

    Returns:
        (ciphertext, iv, tag) — tag is appended to ciphertext by AESGCM,
        but we separate for clarity in storage.
    """
    key = get_settings().encryption_key_bytes
    aesgcm = AESGCM(key)
    iv = os.urandom(12)  # 96-bit nonce, recommended for GCM
    # AESGCM.encrypt returns ciphertext + 16-byte tag appended
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return ciphertext, iv, tag


def decrypt_secret(ciphertext: bytes, iv: bytes, tag: bytes) -> str:
    """Decrypt a secret using AES-256-GCM.

    Returns the plaintext string.
    Raises InvalidTag if tampered or wrong key.
    """
    key = get_settings().encryption_key_bytes
    aesgcm = AESGCM(key)
    ct_with_tag = ciphertext + tag
    plaintext_bytes = aesgcm.decrypt(iv, ct_with_tag, None)
    return plaintext_bytes.decode("utf-8")
