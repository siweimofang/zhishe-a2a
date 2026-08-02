#!/usr/bin/env python3
"""
知设 IP 池化轮换脚本 · V3.0 第二桌面架构
原文支撑:AI 寒武纪《云电脑改变了跑 Cursor 的方式》
"多个 Agent 并发请求模型的时候,不会被你家的宽带卡脖子,IP 池化也避免了单一出口被风控限流。"

特性:
1. 多 IP 池轮换(每 N 次请求切下一个 IP)
2. 429/503 错误自动告警 + 自动切 IP
3. 机房内网通信(同 cn-shanghai)
4. 出口 IP 审计(每周日志)

当前可用 IP 池(待 ICP 备案号 2026-07-08 后申请):
- 39.105.140.201(已分配,主 IP)
- 待申请 5 个公网 IP(同 cn-shanghai 机房)
"""
import os
import sys
import time
import json
import random
import logging
from datetime import datetime, timezone
from collections import defaultdict

# === 配置 ===
IP_POOL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ip_pool.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "ip_rotation.log")

# === 日志 ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ip_rotation")


class IPPoolRotator:
    """IP 池轮换器(铁律 75 v2:默认私有,沙箱实证)

    用法:
        rotator = IPPoolRotator()
        ip = rotator.get_next_ip()  # 轮换下一个 IP
        if rotator.should_rotate():  # 检查是否该切 IP
            ip = rotator.rotate(reason="429_too_many")
    """

    def __init__(self, ip_pool_file: str = IP_POOL_FILE):
        self.ip_pool_file = ip_pool_file
        self.ip_pool = self._load_pool()
        self.current_index = 0
        self.request_count = 0
        self.last_rotate_time = time.time()
        self.error_count = defaultdict(int)  # 按 IP 统计错误
        self.rotate_threshold = 1000  # 每 1000 次请求轮换

    def _load_pool(self) -> list:
        """从 ip_pool.json 加载 IP 池"""
        if not os.path.exists(self.ip_pool_file):
            log.warning(f"IP 池文件不存在: {self.ip_pool_file},使用默认单 IP")
            return ["39.105.140.201"]
        try:
            with open(self.ip_pool_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                ips = data.get("ips", ["39.105.140.201"])
                log.info(f"加载 IP 池: {len(ips)} 个 IP")
                return ips
        except Exception as e:
            log.error(f"IP 池加载失败: {e},使用默认单 IP")
            return ["39.105.140.201"]

    def get_current_ip(self) -> str:
        """获取当前 IP(不轮换)"""
        if not self.ip_pool:
            return "39.105.140.201"
        return self.ip_pool[self.current_index]

    def get_next_ip(self) -> str:
        """轮换到下一个 IP"""
        if len(self.ip_pool) <= 1:
            return self.ip_pool[0] if self.ip_pool else "39.105.140.201"

        self.current_index = (self.current_index + 1) % len(self.ip_pool)
        self.last_rotate_time = time.time()
        log.info(f"IP 轮换: → {self.get_current_ip()}")
        return self.get_current_ip()

    def should_rotate(self) -> bool:
        """判断是否应该轮换 IP"""
        if len(self.ip_pool) <= 1:
            return False
        # 阈值:每 1000 次请求
        if self.request_count >= self.rotate_threshold:
            return True
        return False

    def record_request(self, ip: str, success: bool):
        """记录一次请求的结果"""
        self.request_count += 1
        if not success:
            self.error_count[ip] += 1
            # 错误率 > 5% → 自动切 IP
            if self.error_count[ip] >= 50:
                log.warning(f"IP {ip} 错误数 {self.error_count[ip]},自动切 IP")
                self.get_next_ip()
                self.error_count[ip] = 0

    def rotate(self, reason: str = "manual") -> str:
        """手动切 IP,记录原因"""
        log.info(f"手动切 IP: reason={reason}")
        return self.get_next_ip()

    def get_stats(self) -> dict:
        """获取当前状态"""
        return {
            "current_ip": self.get_current_ip(),
            "pool_size": len(self.ip_pool),
            "request_count": self.request_count,
            "error_count": dict(self.error_count),
            "last_rotate_time": datetime.fromtimestamp(self.last_rotate_time, tz=timezone.utc).isoformat(),
        }


def main():
    """CLI 入口(供 cron 调用)"""
    import argparse

    parser = argparse.ArgumentParser(description="知设 IP 池轮换器")
    parser.add_argument("--action", choices=["status", "rotate", "next"], required=True,
                        help="status=查看状态, rotate=手动切 IP, next=获取下一个 IP")
    parser.add_argument("--reason", default="manual", help="切 IP 的原因")
    args = parser.parse_args()

    rotator = IPPoolRotator()

    if args.action == "status":
        stats = rotator.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        log.info(f"状态查询: {stats}")
    elif args.action == "rotate":
        new_ip = rotator.rotate(reason=args.reason)
        print(f"已切 IP: {new_ip}")
    elif args.action == "next":
        next_ip = rotator.get_next_ip()
        print(f"下一个 IP: {next_ip}")


if __name__ == "__main__":
    main()