"""
Clerk JWT verification for FastAPI.

Clerk handles all the auth UI (sign-in, sign-up, user management) on the
frontend. The backend just needs to verify the JWT token that Clerk attaches
to every request.

How it works:
1. Frontend includes a Bearer token in the Authorization header
2. We fetch Clerk's public keys (JWKS) to verify the token signature
3. If valid, we extract the user ID (the "sub" claim) from the token
4. Route handlers receive the user_id as a dependency

Two dependencies are provided:
- get_current_user: requires auth, raises 401 if not authenticated
- get_optional_user: returns None if not authenticated (for public endpoints)
"""

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request

from app.config import CLERK_JWKS_URL

# Lazily initialized JWKS client. It fetches and caches Clerk's public keys
# so we can verify JWT signatures without calling Clerk on every request.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client for Clerk token verification."""
    global _jwks_client
    if _jwks_client is None:
        if not CLERK_JWKS_URL:
            raise HTTPException(
                status_code=500,
                detail="CLERK_JWKS_URL not configured. Set it in your environment.",
            )
        _jwks_client = PyJWKClient(CLERK_JWKS_URL)
    return _jwks_client


async def get_current_user(request: Request) -> str:
    """
    FastAPI dependency that extracts and verifies the Clerk JWT.

    Returns the user_id (Clerk's "sub" claim) if the token is valid.
    Raises 401 if the token is missing or invalid.

    Usage:
        @router.get("/my-stuff")
        async def my_stuff(user_id: str = Depends(get_current_user)):
            # user_id is guaranteed to be a valid Clerk user ID
            ...
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")

    token = auth_header[7:]
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify token")


async def get_optional_user(request: Request) -> str | None:
    """
    Same as get_current_user but returns None instead of raising 401.

    Use this for endpoints that work for both authenticated and anonymous users
    (e.g., public function invocation).
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
