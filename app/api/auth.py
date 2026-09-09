import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class Credentials(BaseModel):
    username: str
    password: str


def require_user(request: Request) -> dict:
    """FastAPI dependency: resolve the bearer token to a user, else 401.

    Returns ``{user_id, username, session_id}``. ``session_id`` is the single
    scope used for chat history and long-term memory, so data is isolated per
    authenticated user.
    """
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")

    token = header[7:].strip()
    user = auth_service.resolve_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


@router.post("/register")
def register(payload: Credentials):
    try:
        user = auth_service.register_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    token = auth_service.authenticate(payload.username, payload.password)
    if token is None:
        raise HTTPException(status_code=500, detail="Account created but login failed.")
    return {"token": token, "user": user}


@router.post("/login")
def login(payload: Credentials):
    token = auth_service.authenticate(payload.username, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    user = auth_service.resolve_user(token)
    return {"token": token, "user": user}


@router.get("/me")
def me(user: dict = __import__("fastapi").Depends(require_user)):
    return {"user": {"id": user["user_id"], "username": user["username"]}}


@router.post("/logout")
def logout(request: Request, user: dict = Depends(require_user)):
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    auth_service.revoke_token(token)
    return {"status": "logged_out"}
