# 知设 Agent Base Image · V3.0 第二桌面专用
# 基础镜像:Python 3.11 + FastAPI + DeepSeek API + 8 Skill
# 多阶段构建,最终镜像 < 500MB
# 镜像 tag 命名规范:zhishe-agent-base:v{VERSION}-{SKILL_VER}

# ========== Stage 1: Builder ==========
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /build

# 复制依赖文件(单独一层,利用 Docker 缓存)
COPY requirements.txt .

# 升级 pip + 安装 wheel + 安装依赖到 /install 目录
RUN pip install --no-cache-dir --upgrade pip wheel \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    && pip install --no-cache-dir --prefix=/install --no-deps -r requirements.txt

# ========== Stage 2: Runtime ==========
FROM python:3.11-slim AS runtime

# 元数据(沙箱实证可读)
LABEL maintainer="Mavis <Mavis@zhishe.top>" \
      version="1.0.0" \
      description="知设装修顾问 V3.0 第二桌面 · A2A 0.2.5 + 8 Skill" \
      org.opencontainers.image.source="https://tunnel.zhishe.top" \
      org.opencontainers.image.licenses="Proprietary"

# 安全加固:创建非 root 用户(铁律 75 v2 第 7 项:默认私有而非公开)
RUN groupadd -r zhishe && useradd -r -g zhishe -d /app -s /sbin/nologin zhishe

# 设置工作目录
WORKDIR /app

# 设置环境变量(铁律 75 第 7 项:默认私有)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    PORT=8765 \
    # 默认私有:禁止任何接口公网开放(必须显式 opt-in)
    ZHISHE_PUBLIC_NETWORK=false \
    # 默认私有:API Key 必走环境变量,禁止硬编码
    ZHISHE_REQUIRE_ENV_API_KEY=true \
    # 默认私有:日志脱敏必须开启
    ZHISHE_LOG_MASK_PII=true

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制应用代码(显式列出,避免泄露敏感文件)
COPY app/ ./app/
COPY skills/ ./skills/
COPY data/ ./data/
COPY static/ ./static/

# 复制 .env.example(模板,不带真实 key — 铁律 75 第 3 项)
COPY .env.example ./.env.example

# 健康检查(铁律 75 v2 第 6 项:上线前安全扫描)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health').read()" \
    || exit 1

# 切换到非 root 用户(默认私有:降低权限)
USER zhishe

# 暴露端口
EXPOSE 8765

# 启动命令(uvicorn 单 worker — K8s 层面水平扩展)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]