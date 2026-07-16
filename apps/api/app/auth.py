"""Bearer-token authentication against Supabase Auth."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from httpx import HTTPError
from pydantic import BaseModel
from supabase_auth.errors import AuthError

from app.supabase_client import SupabaseNotConfiguredError, create_anon_client

_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Please sign in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


class AuthenticatedUser(BaseModel):
    id: str
    email: str | None
    access_token: str


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    """Resolve the Supabase user behind the request's bearer token.

    The token is verified by Supabase itself rather than decoded locally: this
    service holds no JWT signing secret, and a locally-decoded token would not
    be checked for revocation.
    """
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        client = await create_anon_client()
    except SupabaseNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This server is not connected to its database yet.",
        ) from exc

    try:
        response = await client.auth.get_user(credentials.credentials)
    except AuthError as exc:
        raise _UNAUTHENTICATED from exc
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach the sign-in service. Please try again.",
        ) from exc

    if response is None or response.user is None:
        raise _UNAUTHENTICATED

    return AuthenticatedUser(
        id=response.user.id,
        email=response.user.email,
        access_token=credentials.credentials,
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
