"""
结构化日志 + 响应时间中间件
- 每条日志一行 JSON
- 自动记录每个 HTTP 请求的耗时
- 提供 set_request_id() 给业务层打点用
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# 每个请求的唯一 id(异步安全,中间件设置,业务层读)
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(rid: str | None = None) -> str:
    """业务层调用,设置 / 读取当前 request id"""
    if rid is not None:
        _request_id_var.set(rid)
        return rid
    return _request_id_var.get()


def get_request_id() -> str:
    return _request_id_var.get()


class JsonFormatter(logging.Formatter):
    """一行 JSON 的日志格式,方便 grep / awk 统计"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": get_request_id(),
        }
        # 把 record 里所有"extra_*"开头的字段塞进 JSON
        for key, val in record.__dict__.items():
            if key.startswith("extra_"):
                payload[key[len("extra_"):]] = val
        # 异常信息
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """安装 JSON formatter 到 root logger"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # 清掉 uvicorn 自带的 handler,避免重复输出
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn / fastapi 的子 logger 也走 root
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


class TimingMiddleware(BaseHTTPMiddleware):
    """每个 HTTP 请求自动记录响应时间 + 状态码"""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or f"req-{uuid.uuid4().hex[:8]}"
        token = _request_id_var.set(rid)
        t0 = time.perf_counter()
        log = logging.getLogger("http")
        log.info(
            "request_started",
            extra={
                "extra_method": request.method,
                "extra_path": request.url.path,
                "extra_client": request.client.host if request.client else None,
            },
        )
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            response.headers["X-Request-Id"] = rid
            log.info(
                "request_finished",
                extra={
                    "extra_method": request.method,
                    "extra_path": request.url.path,
                    "extra_status": response.status_code,
                    "extra_latency_ms": round(elapsed_ms, 1),
                },
            )
            return response
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.error(
                "request_failed",
                extra={
                    "extra_method": request.method,
                    "extra_path": request.url.path,
                    "extra_latency_ms": round(elapsed_ms, 1),
                    "extra_error": f"{type(e).__name__}: {e}"[:200],
                },
            )
            raise
        finally:
            _request_id_var.reset(token)