"""Explicit, non-destructive database initialization command."""

from app.seed import initialize_database


if __name__ == "__main__":
    initialize_database()
    print("Database tables and configured admin account ensured without dropping existing data.")
