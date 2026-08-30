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

    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        extra="ignore",
    )


settings = Settings()