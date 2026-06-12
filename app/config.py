"""
配置管理:用 pydantic-settings 读 .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置(从 .env 读)"""
    model_config = SettingsConfigDict(
        env_file=".env",
        # 用 utf-8-sig 自动剥除 .env 文件开头的 UTF-8 BOM(Windows 编辑器常加)
        env_file_encoding="utf-8-sig",
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

    # === 功能开关 ===
    # A2A 流式 SSE 开关:千问支持后,把这个改成 "true" 即可启用,代码不用改
    STREAMING_ENABLED: bool = False

    # === 日志 ===
    LOG_LEVEL: str = "INFO"


settings = Settings()
