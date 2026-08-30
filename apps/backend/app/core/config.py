from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_candidates() -> list[str]:
    current_file = Path(__file__).resolve()
    parents = current_file.parents

    candidates = [
        Path.cwd() / ".env",
    ]

    for parent in parents[:5]:
        candidates.append(parent / ".env")

    return [
        str(path)
        for path in dict.fromkeys(candidates)
        if path.exists()
    ]


class Settings(BaseSettings):
    app_name: str = "PostMesh"
    app_env: str = "development"

    database_url: str
    redis_url: str

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    email_from: str | None = None

    linkedin_api_url: str | None = None
    x_api_url: str | None = None
    facebook_api_url: str | None = None
    instagram_api_url: str | None = None
    threads_api_url: str | None = None
    youtube_api_url: str | None = None
    reddit_api_url: str | None = None
    blog_api_url: str | None = None
    connections_encryption_key: str | None = None
    frontend_url: str = "http://localhost:3000"
    oauth_linkedin_client_id: str | None = None
    oauth_linkedin_client_secret: str | None = None
    oauth_x_client_id: str | None = None
    oauth_x_client_secret: str | None = None
    oauth_facebook_client_id: str | None = None
    oauth_facebook_client_secret: str | None = None

    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        extra="ignore",
    )


settings = Settings()