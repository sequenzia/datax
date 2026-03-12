"""Fernet encryption utilities for encrypting and decrypting sensitive values.

Provides symmetric encryption for API keys, database passwords, and other secrets
using the Fernet scheme from the Python `cryptography` library. The master key is
sourced from the DATAX_ENCRYPTION_KEY environment variable.
"""

import os

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when an encryption or decryption operation fails."""


class InvalidEncryptionKeyError(EncryptionError):
    """Raised when the encryption key is missing or has an invalid format."""


def _load_key() -> bytes:
    """Load and validate the Fernet master key from the environment.

    Returns:
        The raw key bytes suitable for constructing a Fernet instance.

    Raises:
        InvalidEncryptionKeyError: If the key is missing or not a valid Fernet key.
    """
    raw_key = os.environ.get("DATAX_ENCRYPTION_KEY")
    if not raw_key:
        raise InvalidEncryptionKeyError(
            "DATAX_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    key_bytes = raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key

    # Validate by attempting to construct a Fernet instance
    try:
        Fernet(key_bytes)
    except (ValueError, Exception) as exc:
        raise InvalidEncryptionKeyError(
            f"DATAX_ENCRYPTION_KEY is not a valid Fernet key. "
            f"A Fernet key must be 32 url-safe base64-encoded bytes. Error: {exc}"
        ) from exc

    return key_bytes


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the master key from the environment.

    Returns:
        A Fernet instance ready for encrypt/decrypt operations.

    Raises:
        InvalidEncryptionKeyError: If the key is missing or invalid.
    """
    return Fernet(_load_key())


def encrypt_value(plaintext: str) -> bytes:
    """Encrypt a plaintext string using Fernet symmetric encryption.

    Each call produces a different ciphertext because Fernet includes a timestamp
    and uses a random IV (initialization vector) internally.

    Args:
        plaintext: The string value to encrypt.

    Returns:
        The Fernet-encrypted ciphertext as bytes.

    Raises:
        InvalidEncryptionKeyError: If the encryption key is missing or invalid.
        EncryptionError: If encryption fails for any other reason.
    """
    try:
        fernet = _get_fernet()
        return fernet.encrypt(plaintext.encode("utf-8"))
    except InvalidEncryptionKeyError:
        raise
    except Exception as exc:
        raise EncryptionError(f"Failed to encrypt value: {exc}") from exc


def decrypt_value(ciphertext: bytes) -> str:
    """Decrypt a Fernet-encrypted ciphertext back to the original plaintext string.

    Args:
        ciphertext: The Fernet-encrypted bytes to decrypt.

    Returns:
        The original plaintext string.

    Raises:
        InvalidEncryptionKeyError: If the encryption key is missing or invalid.
        EncryptionError: If decryption fails (wrong key, corrupted data, etc.).
    """
    try:
        fernet = _get_fernet()
        return fernet.decrypt(ciphertext).decode("utf-8")
    except InvalidEncryptionKeyError:
        raise
    except InvalidToken:
        raise EncryptionError(
            "Failed to decrypt value: the ciphertext is invalid or was encrypted "
            "with a different key. If the DATAX_ENCRYPTION_KEY was rotated, "
            "previously encrypted values must be re-encrypted with the new key."
        )
    except Exception as exc:
        raise EncryptionError(f"Failed to decrypt value: {exc}") from exc


def validate_encryption_key() -> None:
    """Validate that the encryption key is present and correctly formatted.

    Call this at application startup to fail fast if the key is misconfigured.

    Raises:
        InvalidEncryptionKeyError: If the key is missing or not a valid Fernet key.
    """
    _load_key()
