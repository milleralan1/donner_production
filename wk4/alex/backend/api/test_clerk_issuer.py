import unittest

from fastapi import HTTPException

from auth import validated_clerk_user_id


class ClerkIssuerTests(unittest.TestCase):
    def test_returns_subject_when_issuer_matches(self):
        result = validated_clerk_user_id(
            {
                "iss": "https://example.clerk.accounts.dev/",
                "sub": "user_123",
            },
            "https://example.clerk.accounts.dev",
        )
        self.assertEqual(result, "user_123")

    def test_rejects_untrusted_issuer(self):
        with self.assertRaises(HTTPException) as context:
            validated_clerk_user_id(
                {"iss": "https://attacker.example", "sub": "user_123"},
                "https://example.clerk.accounts.dev",
            )
        self.assertEqual(context.exception.status_code, 401)

    def test_rejects_missing_subject(self):
        with self.assertRaises(HTTPException) as context:
            validated_clerk_user_id({"iss": "https://example.clerk.accounts.dev"})
        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
