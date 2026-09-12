import unittest
from unittest.mock import patch

from src.auth import hash_password, make_session, read_session, verify_password


class AuthTests(unittest.TestCase):
    def test_scrypt_password_hash_round_trip(self):
        encoded = hash_password("correct-horse-battery-staple")

        self.assertTrue(encoded.startswith("scrypt:"))
        self.assertTrue(verify_password("correct-horse-battery-staple", encoded))
        self.assertFalse(verify_password("incorrect", encoded))

    def test_signed_session_rejects_tampering(self):
        session = make_session("viewer", "test-signing-secret")

        self.assertEqual(read_session(session, "test-signing-secret"), "viewer")
        self.assertIsNone(read_session(session + "x", "test-signing-secret"))
        self.assertIsNone(read_session(session, "different-signing-secret"))

    def test_signed_session_expires(self):
        with patch("src.auth.time.time", return_value=1_000):
            session = make_session("admin", "test-signing-secret")

        with patch("src.auth.time.time", return_value=1_000 + 8 * 60 * 60 + 1):
            self.assertIsNone(read_session(session, "test-signing-secret"))


if __name__ == "__main__":
    unittest.main()
