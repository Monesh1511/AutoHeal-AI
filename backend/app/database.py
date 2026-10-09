"""SQLAlchemy engine and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all persistence models."""


database_url = make_url(settings.database_url)
if database_url.drivername == "postgresql":
    database_url = database_url.set(drivername="postgresql+psycopg")

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    """Return whether the configured database accepts a simple query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_db() -> None:
    """Create missing tables without changing existing tables or rows."""
    from app.models import BaseModelRegistry

    BaseModelRegistry.metadata.create_all(bind=engine)
    users_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "role" not in users_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(40) NOT NULL DEFAULT 'user'")
            )
    project_columns = {column["name"] for column in inspect(engine).get_columns("projects")}
    if "github_url" not in project_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE projects ADD COLUMN github_url VARCHAR(500)"))
