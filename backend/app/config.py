"""Application settings loaded from the repository environment file."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr, ValidationError, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    """Validated settings used by backend services."""

    groq_api_key: SecretStr
    groq_model: str = "llama-3.3-70b-versatile"
    auth_secret: str = "local-development-secret-change-me"
    setup_token: str = ""
    approved_workspace: str = str(PROJECT_ROOT / "sample_app")
    admin_email: str = "admin@gmail.com"
    admin_password: SecretStr = SecretStr("admin@123")
    admin_display_name: str = "Aarthi GD"
    admin_role: str = "admin"
    approval_email: str = "aarthi@gmail.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/autoheal"

    @field_validator("groq_api_key")
    @classmethod
    def validate_groq_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("GROQ_API_KEY must not be empty")
        return value

    @classmethod
    def from_environment(cls) -> "Settings":
        """Create settings from environment variables loaded by python-dotenv."""
        import os

        try:
            return cls(
                groq_api_key=os.getenv("GROQ_API_KEY", ""),
                groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                database_url=os.getenv(
                    "DATABASE_URL",
                    "postgresql+psycopg://postgres:postgres@localhost:5432/autoheal",
                ),
                auth_secret=os.getenv(
                    "AUTOHEAL_AUTH_SECRET", "local-development-secret-change-me"
                ),
                setup_token=os.getenv("AUTOHEAL_SETUP_TOKEN", ""),
                approved_workspace=os.getenv(
                    "AUTOHEAL_APPROVED_WORKSPACE", str(PROJECT_ROOT / "sample_app")
                ),
                admin_email=os.getenv("AUTOHEAL_ADMIN_EMAIL", "admin@gmail.com"),
                admin_password=os.getenv("AUTOHEAL_ADMIN_PASSWORD", "admin@123"),
                admin_display_name=os.getenv("AUTOHEAL_ADMIN_DISPLAY_NAME", "Aarthi GD"),
                admin_role=os.getenv("AUTOHEAL_ADMIN_ROLE", "admin"),
                approval_email=os.getenv("AUTOHEAL_APPROVAL_EMAIL", "aarthi@gmail.com"),
                smtp_host=os.getenv("AUTOHEAL_SMTP_HOST", ""),
                smtp_port=int(os.getenv("AUTOHEAL_SMTP_PORT", "587")),
                smtp_username=os.getenv("AUTOHEAL_SMTP_USERNAME", ""),
                smtp_password=os.getenv("AUTOHEAL_SMTP_PASSWORD", ""),
                smtp_from=os.getenv("AUTOHEAL_SMTP_FROM", ""),
            )
        except ValidationError as exc:
            raise RuntimeError(
                "Backend configuration is invalid. Set GROQ_API_KEY in the root .env file."
            ) from exc


settings = Settings.from_environment()
