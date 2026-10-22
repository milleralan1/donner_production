"""Small authorization helpers used after Clerk verifies the JWT signature."""

from typing import Any, Dict

from fastapi import HTTPException


def validated_clerk_user_id(
    decoded: Dict[str, Any], expected_issuer: str = ""
) -> str:
    """Require a verified Clerk subject and, when configured, the expected issuer."""
    issuer = decoded.get("iss")
    issuer = issuer.rstrip("/") if isinstance(issuer, str) else ""
    expected_issuer = expected_issuer.rstrip("/")
    if expected_issuer and issuer != expected_issuer:
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    user_id = decoded.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Token subject is missing")
    return user_id
