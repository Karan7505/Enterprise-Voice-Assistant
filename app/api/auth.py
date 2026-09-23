import asyncio
import logging

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.rate_limiter import check_rate_limit, client_ip
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

SESSION_STORE_UNAVAILABLE = "Session store temporarily unavailable. Please try again."


class Credentials(BaseModel):
    # Restrict the username to a safe charset so it can never carry newlines or
    # whitespace into log lines (log-injection) or produce confusing account
    # names. Every account created before this change already satisfies it, and
    # register_user enforces the same minimum length server-side as defense in
    # depth.
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=8, max_length=128)


def _token_from_request(request: Request) -> str:
    """Session token from the Authorization header (preferred) or the HttpOnly
    auth cookie, so both transports work during the M-5 rollout."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.COOKIE_NAME, "").strip()


def set_auth_cookie(response: Response, token: str) -> None:
    """Deliver the bearer token in an HttpOnly cookie page JS cannot read."""
    response.set_cookie(
        settings.COOKIE_NAME,
        token,
        max_age=settings.TOKEN_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.COOKIE_PATH,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.COOKIE_NAME, path=settings.COOKIE_PATH, samesite=settings.COOKIE_SAMESITE
    )


async def require_user(request: Request) -> dict:
    """FastAPI dependency: resolve the session token (header or cookie) to a
    user, else 401.

    Returns ``{user_id, username, session_id}``. ``session_id`` is the single
    scope used for chat history and long-term memory, so data is isolated per
    authenticated user. The Redis+PostgreSQL resolution runs off the event
    loop so authenticated endpoints stay non-blocking.
    """
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        user = await asyncio.to_thread(auth_service.resolve_user, token)
    except redis.RedisError:
        # Fail-closed: without the shared session store we cannot verify
        # identity, so the request is refused rather than downgraded.
        logger.warning("session store unavailable; refusing authenticated request")
        raise HTTPException(status_code=503, detail=SESSION_STORE_UNAVAILABLE) from None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


def _enforce_login_limit(request: Request) -> None:
    allowed, retry = check_rate_limit(
        "login", client_ip(request), settings.RATE_LIMIT_LOGIN,
        settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait a moment and try again.",
            headers={"Retry-After": str(retry)},
        )


def _enforce_register_limit(request: Request) -> None:
    allowed, retry = check_rate_limit(
        "register", client_ip(request), settings.RATE_LIMIT_REGISTER, 3600
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many account creations. Please try again later.",
            headers={"Retry-After": str(retry)},
        )


@router.post("/register")
def register(payload: Credentials, response: Response, request: Request, _rl=Depends(_enforce_register_limit)):
    ip = client_ip(request)
    if not settings.ALLOW_REGISTRATION:
        logger.info("register blocked (disabled) ip=%s", ip)
        raise HTTPException(status_code=403, detail="Registration is currently disabled.")

    try:
        user = auth_service.register_user(payload.username, payload.password)
    except ValueError:
        # Deliberately generic: do not reveal whether the username exists.
        logger.info("register rejected username=%s ip=%s", payload.username.strip(), ip)
        raise HTTPException(
            status_code=409,
            detail=(
                "We couldn't create an account with those details. "
                "If you already have an account, please sign in."
            ),
        ) from None

    try:
        token = auth_service.authenticate(payload.username, payload.password)
    except redis.RedisError:
        logger.exception("register completed in DB but session store is unavailable")
        raise HTTPException(status_code=503, detail=SESSION_STORE_UNAVAILABLE) from None
    if token is None:
        raise HTTPException(status_code=500, detail="Account created but login failed.")
    set_auth_cookie(response, token)
    logger.info("register success username=%s ip=%s", user["username"], ip)
    return {"token": token, "user": user}


@router.post("/login")
def login(payload: Credentials, response: Response, request: Request, _rl=Depends(_enforce_login_limit)):
    ip = client_ip(request)
    try:
        token = auth_service.authenticate(payload.username, payload.password)
    except redis.RedisError:
        logger.warning("login refused: session store unavailable username=%s ip=%s", payload.username.strip(), ip)
        raise HTTPException(status_code=503, detail=SESSION_STORE_UNAVAILABLE) from None
    if token is None:
        logger.warning("login failed username=%s ip=%s", payload.username.strip(), ip)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    user = auth_service.resolve_user(token)
    set_auth_cookie(response, token)
    logger.info("login success username=%s ip=%s", user["username"], ip)
    return {"token": token, "user": user}


@router.get("/me")
def me(user: dict = Depends(require_user)):
    return {"user": {"id": user["user_id"], "username": user["username"]}}


@router.post("/logout")
def logout(response: Response, request: Request, user: dict = Depends(require_user)):
    auth_service.revoke_token(_token_from_request(request))
    clear_auth_cookie(response)
    return {"status": "logged_out"}
