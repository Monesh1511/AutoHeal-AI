"""Small signed-token authentication layer for the local demo."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        return hmac.compare_digest(
            raw[16:], hashlib.pbkdf2_hmac("sha256", password.encode(), raw[:16], 240_000)
        )
    except (ValueError, IndexError):
        return False


def issue_token(user: User) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": user.id, "exp": int(time.time()) + 3600}).encode()
    ).decode().rstrip("=")
    signature = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def get_authenticated_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        body, signature = authorization[7:].split(".", 1)
        expected = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if payload["exp"] < time.time():
            raise ValueError
        user = db.get(User, int(payload["sub"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_authenticated_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return user
