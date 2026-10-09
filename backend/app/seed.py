"""Idempotent, non-destructive seed helpers for local development."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.models.user import User


def seed_default_admin(db: Session) -> User:
    existing = db.scalar(select(User).where(User.username == settings.admin_email))
    if existing is not None:
        changed = False
        if existing.role != settings.admin_role:
            existing.role = settings.admin_role
            changed = True
        if existing.full_name != settings.admin_display_name:
            existing.full_name = settings.admin_display_name
            changed = True
        if changed:
            db.commit()
        return existing

    admin = User(
        username=settings.admin_email,
        full_name=settings.admin_display_name,
        role=settings.admin_role,
        password_hash=hash_password(settings.admin_password.get_secret_value()),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def initialize_database() -> User:
    from app.database import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        return seed_default_admin(db)


if __name__ == "__main__":
    admin = initialize_database()
    print(f"Database initialized; admin account ensured for {admin.username}.")
