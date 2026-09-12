from unittest.mock import patch

from src.auth import hash_password, make_session, read_session, verify_password


def test_scrypt_password_hash_round_trip():
    encoded = hash_password("correct-horse-battery-staple")

    assert encoded.startswith("scrypt:")
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("incorrect", encoded)


def test_signed_session_rejects_tampering():
    session = make_session("viewer", "test-signing-secret")

    assert read_session(session, "test-signing-secret") == "viewer"
    assert read_session(session + "x", "test-signing-secret") is None
    assert read_session(session, "different-signing-secret") is None


def test_signed_session_expires():
    with patch("src.auth.time.time", return_value=1_000):
        session = make_session("admin", "test-signing-secret")

    with patch("src.auth.time.time", return_value=1_000 + 8 * 60 * 60 + 1):
        assert read_session(session, "test-signing-secret") is None
