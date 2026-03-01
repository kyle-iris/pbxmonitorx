"""AES-256-GCM encryption for PBX credentials.

Security guarantees:
    - 12-byte random nonce per encryption (never reused)
    - 16-byte authentication tag for integrity verification
    - Key never touches disk — only from MASTER_KEY env var
    - Ciphertext, nonce, and tag stored separately for auditability
    - Decryption fails loudly on tamper (InvalidTag exception)
"""

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from src.core.config import get_settings


@dataclass(frozen=True)
class EncryptedBlob:
    """Immutable container for an encrypted value."""
    ciphertext: bytes
    nonce: bytes    # 12 bytes
    tag: bytes      # 16 bytes


def encrypt_password(plaintext: str) -> EncryptedBlob:
    """Encrypt a password string with AES-256-GCM.

    Returns an EncryptedBlob with ciphertext, nonce, and auth tag.
    Each call generates a fresh random nonce.
    """
    key = get_settings().master_key_bytes
    if len(key) != 32:
        raise ValueError("MASTER_KEY must be exactly 32 bytes (64 hex chars)")

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)

    # AESGCM.encrypt appends the 16-byte tag to the ciphertext
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    return EncryptedBlob(ciphertext=ciphertext, nonce=nonce, tag=tag)


def decrypt_password(blob: EncryptedBlob) -> str:
    """Decrypt a password from its encrypted components.

    Raises cryptography.exceptions.InvalidTag if the data was
    tampered with or the wrong key is used.
    """
    key = get_settings().master_key_bytes
    aesgcm = AESGCM(key)
    ct_with_tag = blob.ciphertext + blob.tag
    plaintext_bytes = aesgcm.decrypt(blob.nonce, ct_with_tag, None)
    return plaintext_bytes.decode("utf-8")


def rotate_key(old_key_hex: str, new_key_hex: str,
               ciphertext: bytes, nonce: bytes, tag: bytes) -> EncryptedBlob:
    """Re-encrypt a credential with a new master key.

    Used during key rotation. Decrypts with old key, encrypts with new.
    """
    old_key = bytes.fromhex(old_key_hex)
    new_key = bytes.fromhex(new_key_hex)

    # Decrypt with old key
    old_aesgcm = AESGCM(old_key)
    plaintext = old_aesgcm.decrypt(nonce, ciphertext + tag, None).decode("utf-8")

    # Encrypt with new key
    new_aesgcm = AESGCM(new_key)
    new_nonce = os.urandom(12)
    ct_with_tag = new_aesgcm.encrypt(new_nonce, plaintext.encode("utf-8"), None)

    return EncryptedBlob(
        ciphertext=ct_with_tag[:-16],
        nonce=new_nonce,
        tag=ct_with_tag[-16:],
    )
