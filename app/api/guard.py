"""
知设防护模块 guard.py (2026-08-06)
====================================
三层防护,对应三类攻击:

反调取(API 滥用):
  - 滑动窗口限流:每 IP 30 次/分 + 每 Key 120 次/分,超限返回 429
  - prompt 长度上限 2000 字符,防超长批量倒库

反拆解(提示词/知识库套取):
  - 探测识别:系统提示词套取 / 知识库整库导出类 prompt
  - 命中后不直接拒绝(避免暴露防护存在),返回标准话术 + 告警日志

反扒(回答内容被复制/训练):
  - 回答尾注水印(品牌 + 免责声明,可配置关闭)
  - 探测命中与限流事件均写入结构化日志,便于事后审计

用法:
  from app.api import guard
  allowed, reason = guard.rate_limit(client_ip, api_key)
  kind = guard.detect_probe(prompt)
  text = guard.apply_watermark(text)
"""
import logging
import re
import threading
import time
from collections import defaultdict, deque

log = logging.getLogger("guard")

# ==================== 配置(直接改这里,无需重启改 .env) ====================
RATE_LIMIT_PER_MIN_IP = 30      # 每 IP 每分钟请求上限(百炼单应用正常远低于此)
RATE_LIMIT_PER_MIN_KEY = 120    # 每 Key 每分钟请求上限(跨 IP 汇总)
WINDOW_SECONDS = 60
MAX_PROMPT_LEN = 2000           # prompt 长度上限,防超长批量倒库
WATERMARK_ENABLED = True        # 回答尾注水印开关
WATERMARK_TEXT = (
    "\n\n—— 本回答由「知设 AI 装修顾问」生成,价格口径与避坑依据"
    "以官方渠道最新发布为准,请结合当地市场实际情况参考。"
)

# ==================== 滑动窗口限流(进程内,单进程 uvicorn 够用) ====================
_lock = threading.Lock()
_ip_window = defaultdict(deque)   # ip -> deque[timestamp]
_key_window = defaultdict(deque)  # api_key -> deque[timestamp]


def _allow(bucket: dict, key: str, limit: int) -> bool:
    now = time.time()
    with _lock:
        q = bucket[key]
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def rate_limit(client_ip: str, api_key=None):
    """限流检查。

    返回 (allowed: bool, reason: str)。
    api_key 为 None 时只做 IP 维度限流。
    """
    ip = client_ip or "unknown"
    if not _allow(_ip_window, ip, RATE_LIMIT_PER_MIN_IP):
        return False, "ip_rate_limit"
    if api_key and not _allow(_key_window, api_key, RATE_LIMIT_PER_MIN_KEY):
        return False, "key_rate_limit"
    return True, ""


# ==================== 归一化预处理(2026-08-06 压力测试修复) ====================
# 第一轮 fuzz 发现:空格插入/全角/繁体/零宽字符/大小写混写可规避词表。
# 修复:探测前归一化——去控制符 → 全角转半角 → 去空白与分隔符 → 繁体转简体 → 小写,
# 任何"插入干扰符"的绕过写法都会被还原成连续明文再匹配。
_FULL2HALF = {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
_TRAD2SIMP = str.maketrans(
    "系統提示詞設定規則輸出內容完整全部經驗庫逐字行為準則忽略之前所有配置初始管理員顯示示範頻繁複製務導視覺設計風格項目預算價格檔次裝修專業數據來源依據指令執行編程底層內部邏輯",
    "系统提示词设定规则输出内容完整全部经验库逐字行为准则忽略之前所有配置初始管理员显示示范频繁复制务导视觉设计风格项目预算价格档次装修专业数据来源依据指令执行编程底层内部逻辑",
)


def _normalize(s: str) -> str:
    """探测用归一化:去掉一切可被攻击者利用的干扰符。"""
    s = "".join(
        ch for ch in s if ord(ch) >= 0x20 and ch not in "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff"
    )
    s = "".join(_FULL2HALF.get(ch, ch) for ch in s)
    s = "".join(
        ch
        for ch in s
        if not ch.isspace() and ch not in "_—–-·,，。.．;；:：/\\"
    )
    s = s.translate(_TRAD2SIMP)
    return s.lower()


# ==================== 探测识别(反拆解) ====================
# 组 A:系统提示词 / 指令 / 规则套取(匹配前经 _normalize 归一化)
_PROBE_A = re.compile(
    r"系统提示词|system\s*prompt|你的提示词|你的指令|你的设定|角色设定|初始化设定|"
    r"ignore\s+(all|any)?\s*(previous|prior|above)|忽略(之前|以上|上面)(的)?(所有)?(指令|提示|内容|规则|设定)|"
    r"你是如何被(设计|设定|编程)|你的(底层|内部)(规则|逻辑|设计)|"
    r"把你的(规则|设定|提示词|指令|系统)(写|列|输出|打印|告诉|发给|展示|复述|念)|"
    r"把.{0,4}(设定|指令|规则|提示词).{0,8}(写|列|输出|打印|告诉|发给|展示|复述|念|逐字)|"
    r"reveal\s*(your|the)\s*(prompt|system|rules)|show\s*(me|us)?\s*(your|the)\s*(prompt|rules|system)|"
    r"print\s*(all\s*)?(your\s*)?(the\s*)?(prompt|rules|instructions|system)|"
    r"你的(系统)?提示词(是)?什么|prompt\s*of\s*yours|"
    r"(行为准则|行动准则|工作准则|指令集|配置信息|初始配置|系统配置).{0,6}(第|是什么|有哪些|念|写|输出|展示|全部)|"
    r"(管理员|开发者|官方|运维|老板|上级).{0,12}(配置|设定|规则|提示词|指令|行为准则)|"
    r"在.{0,10}(什么|哪些).{0,6}(规则|指令|设定|配置).{0,8}(工作|运行|执行|下)|"
    r"(规则|指令|设定|配置).{0,4}(念|背|说|复述|演示)一遍",
    re.I,
)

# 组 B:知识库整库导出(匹配前经 _normalize 归一化)
_PROBE_B = re.compile(
    r"完整输出|全部输出|输出全部|导出(全部|整个|完整)|"
    r"全部(内容|数据|规则|条目|记录|信息|资料|经验|案例|列表).{0,6}(输出|列出|导出|给我|展示|复制)|"
    r"所有.{0,4}(规则|条目|设定|指令|数据|经验)|"
    r"逐条|所有条目|完整(库|列表|内容|版本)|"
    r"gotchas|避坑(库|经验|知识).{0,10}(完整|全部|导出|内容|列表|一条不落)|"
    r"532\s*条|dump\s*(all|everything)|extract\s*(all|the\s*(full|entire))",
    re.I,
)

# 命中后的标准话术:不拒绝 HTTP(不暴露防护),引导回业务
PROBE_REPLY = (
    "这个问题涉及知设的内部配置信息,不便对外提供。"
    "如果您需要装修报价估算、报价构成、避坑要点或施工流程与验收标准方面的建议,我可以为您详细解答。"
)


def detect_probe(prompt: str) -> str:
    """探测识别。返回 'none' | 'prompt_extract' | 'ku_dump'。"""
    if not prompt:
        return "none"
    norm = _normalize(prompt)
    if _PROBE_A.search(norm):
        return "prompt_extract"
    if _PROBE_B.search(norm):
        return "ku_dump"
    return "none"


# ==================== 响应水印(反扒) ====================
def apply_watermark(text: str) -> str:
    """回答末尾追加品牌+免责尾注(幂等,防重复叠加)。"""
    if not WATERMARK_ENABLED or not text:
        return text
    if WATERMARK_TEXT.strip() in text:
        return text
    return text + WATERMARK_TEXT
