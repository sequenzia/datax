import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.encryption import (
    EncryptionError,
    InvalidEncryptionKeyError,
    decrypt_value,
    encrypt_value,
    validate_encryption_key,
)

# Generate a valid Fernet key for tests
TEST_KEY = Fernet.generate_key().decode()
ALT_KEY = Fernet.generate_key().decode()


def _env_with_key(key: str = TEST_KEY) -> dict[str, str]:
    """Return a minimal environment dict with the given encryption key."""
    return {"DATAX_ENCRYPTION_KEY": key}


class TestRoundTrip:
    """encrypt_value -> decrypt_value preserves the original plaintext."""

    def test_basic_round_trip(self) -> None:
        """Encrypting then decrypting recovers the original string."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            plaintext = "my-secret-api-key-12345"
            ciphertext = encrypt_value(plaintext)
            assert decrypt_value(ciphertext) == plaintext

    def test_empty_string_round_trip(self) -> None:
        """Empty string encrypts and decrypts correctly."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            ciphertext = encrypt_value("")
            assert decrypt_value(ciphertext) == ""

    def test_unicode_round_trip(self) -> None:
        """Non-ASCII / Unicode strings encrypt and decrypt correctly."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            plaintext = "mot de passe: cafe\u0301 \u2603 \U0001f512"
            ciphertext = encrypt_value(plaintext)
            assert decrypt_value(ciphertext) == plaintext

    def test_long_string_round_trip(self) -> None:
        """Very long strings (10KB+) encrypt and decrypt correctly."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            plaintext = "x" * 12_000  # ~12 KB
            ciphertext = encrypt_value(plaintext)
            assert decrypt_value(ciphertext) == plaintext


class TestNonDeterministic:
    """Fernet encryption is non-deterministic (timestamp + random IV)."""

    def test_different_ciphertexts_for_same_plaintext(self) -> None:
        """Encrypting the same plaintext twice produces different ciphertexts."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            plaintext = "same-secret"
            ct1 = encrypt_value(plaintext)
            ct2 = encrypt_value(plaintext)
            assert ct1 != ct2

    def test_different_plaintexts_produce_different_ciphertexts(self) -> None:
        """Different plaintexts always produce different ciphertexts."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            ct_a = encrypt_value("secret-a")
            ct_b = encrypt_value("secret-b")
            assert ct_a != ct_b


class TestEncryptProducesBytes:
    """encrypt_value returns Fernet-encrypted bytes."""

    def test_encrypt_returns_bytes(self) -> None:
        """The return type of encrypt_value is bytes."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            result = encrypt_value("hello")
            assert isinstance(result, bytes)

    def test_encrypted_bytes_are_valid_fernet_token(self) -> None:
        """The encrypted output is a valid Fernet token decodable by Fernet."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            ciphertext = encrypt_value("hello")
            fernet = Fernet(TEST_KEY.encode())
            assert fernet.decrypt(ciphertext) == b"hello"


class TestMissingKey:
    """Missing DATAX_ENCRYPTION_KEY raises a clear startup error."""

    def test_encrypt_without_key_raises_error(self) -> None:
        """encrypt_value raises InvalidEncryptionKeyError when key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="DATAX_ENCRYPTION_KEY.*not set"):
                encrypt_value("secret")

    def test_decrypt_without_key_raises_error(self) -> None:
        """decrypt_value raises InvalidEncryptionKeyError when key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="DATAX_ENCRYPTION_KEY.*not set"):
                decrypt_value(b"some-ciphertext")

    def test_validate_without_key_raises_error(self) -> None:
        """validate_encryption_key raises InvalidEncryptionKeyError when key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="DATAX_ENCRYPTION_KEY.*not set"):
                validate_encryption_key()

    def test_empty_key_raises_error(self) -> None:
        """An empty string key is treated as missing."""
        with patch.dict(os.environ, {"DATAX_ENCRYPTION_KEY": ""}, clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="DATAX_ENCRYPTION_KEY.*not set"):
                encrypt_value("secret")


class TestInvalidKeyFormat:
    """Invalid Fernet key format raises a descriptive error."""

    def test_short_key_raises_error(self) -> None:
        """A key that is too short raises InvalidEncryptionKeyError."""
        with patch.dict(os.environ, _env_with_key("too-short"), clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="not a valid Fernet key"):
                encrypt_value("secret")

    def test_non_base64_key_raises_error(self) -> None:
        """A key with invalid base64 characters raises InvalidEncryptionKeyError."""
        with patch.dict(os.environ, _env_with_key("!!not-valid-base64!!"), clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="not a valid Fernet key"):
                encrypt_value("secret")

    def test_validate_invalid_key_raises_descriptive_error(self) -> None:
        """validate_encryption_key raises a descriptive error for bad keys."""
        with patch.dict(os.environ, _env_with_key("invalid"), clear=True):
            with pytest.raises(InvalidEncryptionKeyError, match="not a valid Fernet key"):
                validate_encryption_key()

    def test_validate_valid_key_succeeds(self) -> None:
        """validate_encryption_key succeeds silently with a valid key."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            validate_encryption_key()  # Should not raise


class TestWrongKeyDecryption:
    """Decryption with a different key raises a clear error."""

    def test_wrong_key_raises_encryption_error(self) -> None:
        """Decrypting with a different key raises EncryptionError."""
        with patch.dict(os.environ, _env_with_key(TEST_KEY), clear=True):
            ciphertext = encrypt_value("my-secret")

        with patch.dict(os.environ, _env_with_key(ALT_KEY), clear=True):
            with pytest.raises(EncryptionError, match="different key"):
                decrypt_value(ciphertext)


class TestCorruptedCiphertext:
    """Corrupted ciphertext raises a clear error."""

    def test_garbage_bytes_raises_error(self) -> None:
        """Completely invalid ciphertext raises EncryptionError."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            with pytest.raises(EncryptionError, match="invalid"):
                decrypt_value(b"this-is-not-valid-ciphertext")

    def test_truncated_ciphertext_raises_error(self) -> None:
        """Truncated ciphertext raises EncryptionError."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            ciphertext = encrypt_value("secret")
            truncated = ciphertext[:10]
            with pytest.raises(EncryptionError, match="invalid"):
                decrypt_value(truncated)

    def test_modified_ciphertext_raises_error(self) -> None:
        """Modified ciphertext (flipped byte) raises EncryptionError."""
        with patch.dict(os.environ, _env_with_key(), clear=True):
            ciphertext = encrypt_value("secret")
            # Flip a byte in the middle of the ciphertext
            modified = bytearray(ciphertext)
            mid = len(modified) // 2
            modified[mid] = (modified[mid] + 1) % 256
            with pytest.raises(EncryptionError):
                decrypt_value(bytes(modified))
