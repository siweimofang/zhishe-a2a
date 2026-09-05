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

    # === 主力模型选择 (2026-08-20 百炼迁移) ===
    # 可选值: deepseek | bailian
    # 切换主力模型只需改这一行，无需改代码
    PRIMARY_MODEL: str = "deepseek"

    # === DeepSeek-V4-Pro ===
    DEEPSEEK_API_KEY: str = ""

    # === 千问 A2A 鉴权 ===
    A2A_API_KEY: str = ""

    # === Gotchas 管理端点独立鉴权(2026-08-17) ===
    # 与 A2A_API_KEY 分离:管理端点可热更新/回滚规则,权限面更大。
    # 未配置 → 管理端点整体不可用(安全默认,不本地放行)。
    A2A_ADMIN_KEY: str = ""

    # === 千问百炼 API(2026-08-17) ===
    BAILIAN_API_KEY: str = ""
    BAILIAN_BASE_URL: str = "https://llm-fjhp3zgzyusrt8vy.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    BAILIAN_MODEL: str = "qwen3.8-max"

    # === 智谱 GLM-4-Flash 免费兜底(2026-08-26) ===
    # 当百炼+DeepSeek 都负载高时, 用免费的 GLM-4-Flash 兜底, 至少用户不看到"服务不可用"
    ZHIPU_API_KEY: str = ""
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL: str = "glm-4-flash"

    # === 服务 ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # === 功能开关 ===
    # A2A 流式 SSE 开关:千问支持后,把这个改成 "true" 即可启用,代码不用改
    STREAMING_ENABLED: bool = False

    # === 日志 ===
    LOG_LEVEL: str = "INFO"

    # === 测试模式(小艺平台审核用) ===
    # true=所有端点跳过鉴权,返回预设回复(仅用于平台测试,生产环境必须false)
    TEST_MODE: bool = False

    # === 测试端点预设回复(小艺平台审核用) ===
    TEST_REPLY: str = (
        "您好！我是知设AI装修顾问。根据您提供的信息，以下是专业建议：\n\n"
        "【装修报价参考】\n"
        "以沈阳市场为例，90㎡半包装修参考价格区间为6-9万元，其中：\n"
        "- 人工费：约2.5-3.5万元（水电、瓦工、木工、油漆）\n"
        "- 辅材费：约1-1.5万元（水泥、沙子、电线、水管）\n"
        "- 管理费：约0.5-1万元\n\n"
        "【避坑提醒】\n"
        "1. 水电改造注意：避免绕线计米，要求点对点直线走线\n"
        "2. 防水施工：卫生间防水至少刷2遍，闭水试验48小时以上\n"
        "3. 橱柜台面：避免用人造石，易渗色开裂，建议选石英石\n\n"
        "以上数据基于2026年Q2全国装修市场调研，仅供参考。"
    )


settings = Settings()
