"""
配置管理:用 pydantic-settings 读 .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置(从 .env 读)"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 主力模型:DeepSeek-V4-Pro ===
    DEEPSEEK_API_KEY: str = ""

    # === 千问 A2A 鉴权 ===
    A2A_API_KEY: str = ""

    # === 服务 ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # === 日志 ===
    LOG_LEVEL: str = "INFO"


settings = Settings()
