"""
成本路由器 (2026-08-20)

根据峰谷时段 + 任务复杂度 + 缓存状态, 自动选择性价比最高的模型。

全市场定价横评 (元/百万 tokens, 2026-08-20 确认):

旗舰级:
  DeepSeek V4-Pro   谷 4.5/13.5  峰 9/27      缓存命中 谷0.15/峰0.30 性价比之王
  Qwen3.8-Max       固定 12/36   缓存 1.2      夜间0.2折(2.4/7.2)
  MiniMax M2.7      永久5折 2.1/8.4  缓存 0.42
  GLM-5.2           ~10/~32
  Kimi K3           20/100       缓存 2        最贵

中端:
  Doubao Seed 2.0-Pro  3.2/16
  MiMo-V2-Flash        0.7/2.1
  Qwen3.5-Plus         0.8/4.8

轻量/免费:
  DeepSeek V4-Flash    谷 1.5/4.5  峰 3/9     缓存命中 谷0.05/峰0.10
  豆包 Seed 1.6-Flash  0.075/0.75              全场最低标价
  Qwen-Turbo           0.3/0.6
  GLM-4-Flash          免费
  混元 Lite            免费

核心发现:
  知设场景系统提示词固定(~1200t), DeepSeek cache hit 后输入成本趋近于零
  典型问答(2100入+350出): V4-Pro 缓存命中 0.0004元/次, 比百炼便宜 94 倍
  日常用 DeepSeek 系列, 数据合规/复杂创作才用百炼
"""
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("cost_router")

# 北京时间
BJT = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 全市场定价表 (元/百万 tokens, 2026-08-20)
# peak/valley 仅对有峰谷机制的模型有效, 无峰谷模型 peak=valley
# ---------------------------------------------------------------------------

PRICING = {
    # === DeepSeek 系列 (峰谷定价, 高峰 9-12/14-18 北京) ===
    "deepseek-v4-pro": {
        "peak":  {"cache_hit_input": 0.30, "cache_miss_input": 9.0,  "output": 27.0},
        "valley": {"cache_hit_input": 0.15, "cache_miss_input": 4.5,  "output": 13.5},
        "quality": "high",
        "provider": "deepseek",
        "strengths": ["报价计算", "专业问答", "数字精确", "缓存极便宜"],
        "has_peak_valley": True,
    },
    "deepseek-v4-flash": {
        "peak":  {"cache_hit_input": 0.10, "cache_miss_input": 3.0,  "output": 9.0},
        "valley": {"cache_hit_input": 0.05, "cache_miss_input": 1.5,  "output": 4.5},
        "quality": "medium",
        "provider": "deepseek",
        "strengths": ["简单问答", "闲聊", "快速回复", "极致低价"],
        "has_peak_valley": True,
    },

    # === 阿里百炼系列 (固定价, 无峰谷) ===
    "qwen3.8-max": {
        "peak":  {"cache_hit_input": 1.2,  "cache_miss_input": 12.0, "output": 36.0},
        "valley": {"cache_hit_input": 1.2,  "cache_miss_input": 12.0, "output": 36.0},
        "quality": "premium",
        "provider": "bailian",
        "strengths": ["长文创作", "数据合规(阿里生态内)", "复杂推理"],
        "has_peak_valley": False,
    },
    "qwen3.5-plus": {
        "peak":  {"cache_hit_input": 0.08, "cache_miss_input": 0.8,  "output": 4.8},
        "valley": {"cache_hit_input": 0.08, "cache_miss_input": 0.8,  "output": 4.8},
        "quality": "medium-high",
        "provider": "bailian",
        "strengths": ["通用问答", "阿里生态", "中端性价比"],
        "has_peak_valley": False,
    },

    # === MiniMax (永久5折, 无峰谷) ===
    "minimax-m2.7": {
        "peak":  {"cache_hit_input": 0.42, "cache_miss_input": 2.1,  "output": 8.4},
        "valley": {"cache_hit_input": 0.42, "cache_miss_input": 2.1,  "output": 8.4},
        "quality": "high",
        "provider": "minimax",
        "strengths": ["高质量", "中端价位", "长上下文"],
        "has_peak_valley": False,
    },

    # === 豆包/字节 (无峰谷) ===
    "doubao-seed-2.0-pro": {
        "peak":  {"cache_hit_input": 0.32, "cache_miss_input": 3.2,  "output": 16.0},
        "valley": {"cache_hit_input": 0.32, "cache_miss_input": 3.2,  "output": 16.0},
        "quality": "high",
        "provider": "doubao",
        "strengths": ["通用旗舰", "字节生态"],
        "has_peak_valley": False,
    },
    "doubao-seed-1.6-flash": {
        "peak":  {"cache_hit_input": 0.0075, "cache_miss_input": 0.075, "output": 0.75},
        "valley": {"cache_hit_input": 0.0075, "cache_miss_input": 0.075, "output": 0.75},
        "quality": "low-medium",
        "provider": "doubao",
        "strengths": ["全场最低标价", "超轻量"],
        "has_peak_valley": False,
    },

    # === 智谱 (免费) ===
    "glm-4-flash": {
        "peak":  {"cache_hit_input": 0, "cache_miss_input": 0, "output": 0},
        "valley": {"cache_hit_input": 0, "cache_miss_input": 0, "output": 0},
        "quality": "low",
        "provider": "zhipu",
        "strengths": ["完全免费", "零成本"],
        "has_peak_valley": False,
    },
}

# 高峰时段定义 (北京时间, DeepSeek 专用)
PEAK_HOURS = [(9, 12), (14, 18)]


# ---------------------------------------------------------------------------
# 时段判断
# ---------------------------------------------------------------------------

def is_peak_hour() -> bool:
    """判断当前是否为 DeepSeek 高峰时段 (北京时间)"""
    now = datetime.now(BJT)
    hour = now.hour
    for start, end in PEAK_HOURS:
        if start <= hour < end:
            return True
    return False


def get_period() -> str:
    """返回当前时段: peak | valley"""
    return "peak" if is_peak_hour() else "valley"


# ---------------------------------------------------------------------------
# 成本计算
# ---------------------------------------------------------------------------

def estimate_cost(
    model: str,
    input_tokens: int = 2100,
    output_tokens: int = 350,
    cache_hit: bool = True,
    period: str = None,
) -> float:
    """
    估算单次调用成本 (元)。

    Args:
        model: 模型标识 (PRICING 中的 key)
        input_tokens: 输入 token 数 (默认 2100 = 知设典型问答)
        output_tokens: 输出 token 数 (默认 350)
        cache_hit: 是否命中 prompt cache
        period: 指定时段, None 则自动判断当前时段

    Returns:
        预估成本 (元)
    """
    if model not in PRICING:
        return 999.0

    p = period or get_period()
    prices = PRICING[model][p]

    if cache_hit:
        input_cost = input_tokens * prices["cache_hit_input"] / 1_000_000
    else:
        input_cost = input_tokens * prices["cache_miss_input"] / 1_000_000

    output_cost = output_tokens * prices["output"] / 1_000_000
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# 任务复杂度分类
# ---------------------------------------------------------------------------

def classify_task(user_text: str, max_tokens: int, has_quote: bool) -> str:
    """
    判断任务复杂度。

    Returns:
        simple   -> 闲聊/打招呼/简单FAQ
        standard -> 报价问答/专业咨询
        complex  -> 长文创作 (max_tokens > 500)
    """
    if max_tokens > 500:
        return "complex"

    text = user_text.strip()
    text_len = len(text)

    # 简单交互
    if text_len <= 6:
        return "simple"
    simple_keywords = [
        "你好", "在吗", "谢谢", "再见", "嗯", "好的", "嗯嗯",
        "你是谁", "你是", "能做什么", "哈哈", "666",
    ]
    if any(kw in text for kw in simple_keywords):
        return "simple"

    # 有报价数据 -> standard
    if has_quote:
        return "standard"

    # 装修相关短问 -> standard (大多数场景)
    if text_len >= 4:
        return "standard"

    return "simple"


# ---------------------------------------------------------------------------
# 智能路由 (核心)
# ---------------------------------------------------------------------------

def select_model(
    user_text: str = "",
    max_tokens: int = 350,
    has_quote: bool = False,
    force_model: str = None,
    prefer_compliance: bool = False,
) -> dict:
    """
    选择性价比最高的模型。

    路由策略 (2026-08-20):
    +-------------+----------------------+------------------------+------------+
    | 任务类型     | 首选模型              | 兜底模型                | 单次成本   |
    +-------------+----------------------+------------------------+------------+
    | simple      | V4-Flash (cache)     | V4-Pro (cache)         | ~0.0001    |
    | standard    | V4-Pro (cache)       | V4-Flash (cache)       | ~0.0004    |
    | complex     | V4-Pro (cache)       | Qwen3.8-Max            | ~0.005     |
    | compliance  | Qwen3.8-Max          | Qwen3.5-Plus           | ~0.038     |
    +-------------+----------------------+------------------------+------------+

    Args:
        user_text: 用户原始输入
        max_tokens: 最大输出 tokens
        has_quote: 是否注入了报价数据
        force_model: 强制指定模型 (跳过路由)
        prefer_compliance: 是否优先数据合规 (走阿里生态)

    Returns:
        dict with model, provider, reason, estimated_cost, fallback_model, etc.
    """
    period = get_period()

    # 强制指定
    if force_model and force_model in PRICING:
        info = PRICING[force_model]
        return {
            "model": force_model,
            "provider": info["provider"],
            "reason": "force_model=" + force_model,
            "estimated_cost": estimate_cost(force_model, period=period),
            "fallback_model": None,
            "fallback_provider": None,
            "task_type": "forced",
            "period": period,
        }

    task = classify_task(user_text, max_tokens, has_quote)

    # --- 数据合规优先 -> 百炼 ---
    if prefer_compliance:
        cost = estimate_cost("qwen3.8-max", period=period)
        return {
            "model": "qwen3.8-max",
            "provider": "bailian",
            "reason": "compliance mode -> Qwen3.8-Max (data in Alibaba cloud)",
            "estimated_cost": cost,
            "fallback_model": "qwen3.5-plus",
            "fallback_provider": "bailian",
            "task_type": task,
            "period": period,
        }

    # --- simple: V4-Flash 极致性价比 ---
    if task == "simple":
        cost_flash = estimate_cost("deepseek-v4-flash", period=period, cache_hit=True)
        cost_pro = estimate_cost("deepseek-v4-pro", period=period, cache_hit=True)
        saving_pct = int((1 - cost_flash / max(cost_pro, 0.000001)) * 100)
        return {
            "model": "deepseek-v4-flash",
            "provider": "deepseek",
            "reason": "simple -> V4-Flash %.6f yuan/call (save %d%% vs V4-Pro)" % (cost_flash, saving_pct),
            "estimated_cost": cost_flash,
            "fallback_model": "deepseek-v4-pro",
            "fallback_provider": "deepseek",
            "task_type": task,
            "period": period,
        }

    # --- standard: V4-Pro 缓存命中是性价比之王 ---
    if task == "standard":
        cost_pro = estimate_cost("deepseek-v4-pro", period=period, cache_hit=True)
        cost_qwen = estimate_cost("qwen3.8-max", period=period, cache_hit=False)
        saving_pct = int((1 - cost_pro / max(cost_qwen, 0.000001)) * 100)
        return {
            "model": "deepseek-v4-pro",
            "provider": "deepseek",
            "reason": "standard, %sh, cache -> V4-Pro %.6f yuan/call (save %d%% vs bailian)" % (period, cost_pro, saving_pct),
            "estimated_cost": cost_pro,
            "fallback_model": "deepseek-v4-flash",
            "fallback_provider": "deepseek",
            "task_type": task,
            "period": period,
        }

    # --- complex: V4-Pro 质量足够, 比百炼便宜 10 倍+ ---
    cost_pro = estimate_cost("deepseek-v4-pro", period=period, cache_hit=True)
    cost_qwen = estimate_cost("qwen3.8-max", period=period, cache_hit=False)
    saving_pct = int((1 - cost_pro / max(cost_qwen, 0.000001)) * 100)
    return {
        "model": "deepseek-v4-pro",
        "provider": "deepseek",
        "reason": "complex, %sh -> V4-Pro %.6f yuan/call (save %d%% vs bailian)" % (period, cost_pro, saving_pct),
        "estimated_cost": cost_pro,
        "fallback_model": "qwen3.8-max",
        "fallback_provider": "bailian",
        "task_type": task,
        "period": period,
    }


# ---------------------------------------------------------------------------
# 成本统计
# ---------------------------------------------------------------------------

class CostTracker:
    """累计成本追踪器 (进程内)"""

    def __init__(self):
        self.total_cost = 0.0
        self.total_requests = 0
        self.model_usage = {}
        self.daily_cost = {}

    def record(self, model: str, cost: float):
        self.total_cost += cost
        self.total_requests += 1
        self.model_usage[model] = self.model_usage.get(model, 0) + 1
        today = datetime.now(BJT).strftime("%Y-%m-%d")
        self.daily_cost[today] = self.daily_cost.get(today, 0.0) + cost

    def summary(self) -> dict:
        today = datetime.now(BJT).strftime("%Y-%m-%d")
        avg = self.total_cost / max(self.total_requests, 1)
        return {
            "total_cost_yuan": round(self.total_cost, 6),
            "total_requests": self.total_requests,
            "avg_cost_per_request": round(avg, 6),
            "today_cost_yuan": round(self.daily_cost.get(today, 0.0), 6),
            "model_usage": self.model_usage,
            "current_period": get_period(),
            "is_peak": is_peak_hour(),
        }


tracker = CostTracker()


# ---------------------------------------------------------------------------
# 全景对比报告
# ---------------------------------------------------------------------------

def pricing_report() -> str:
    """生成全市场价格对比报告"""
    lines = [
        "=" * 72,
        "知设 AI 装修顾问 - 全模型成本横评 (2026-08-20)",
        "=" * 72,
        "",
        "典型查询: 输入 ~2100t (system 1200 + kb 800 + user 100), 输出 ~350t",
        "",
    ]

    header = "%-22s %-4s %-4s %10s %8s %6s" % ("模型", "时段", "缓存", "单次成本", "vs最贵", "质量")
    lines.append(header)
    lines.append("-" * 72)

    configs = [
        ("deepseek-v4-flash",     "valley", True),
        ("deepseek-v4-flash",     "peak",   True),
        ("deepseek-v4-pro",       "valley", True),
        ("deepseek-v4-pro",       "peak",   True),
        ("deepseek-v4-pro",       "peak",   False),
        ("doubao-seed-1.6-flash", "valley", False),
        ("qwen3.5-plus",          "valley", False),
        ("minimax-m2.7",          "valley", True),
        ("doubao-seed-2.0-pro",   "valley", False),
        ("qwen3.8-max",           "valley", False),
        ("glm-4-flash",           "valley", False),
    ]

    costs = []
    for model, period, cache in configs:
        costs.append(estimate_cost(model, 2100, 350, cache, period))
    max_cost = max(c for c in costs if c > 0)

    for i, (model, period, cache) in enumerate(configs):
        cost = costs[i]
        p_cn = "峰" if period == "peak" else "谷"
        c_cn = "命中" if cache else "未中"
        q = PRICING[model]["quality"]
        if cost == 0:
            saving = "免费"
        elif cost < max_cost:
            saving = "省%d%%" % int((1 - cost / max_cost) * 100)
        else:
            saving = "基准"
        lines.append("%-22s %-4s %-4s %10.6f %8s %6s" % (model, p_cn, c_cn, cost, saving, q))

    lines += [
        "-" * 72,
        "",
        "路由策略 (推荐):",
        "  simple  (闲聊)      -> V4-Flash     ~ 0.0001 yuan/call",
        "  standard (专业问答)  -> V4-Pro       ~ 0.0004 yuan/call (cache hit)",
        "  complex  (长文)      -> V4-Pro       ~ 0.005 yuan/call",
        "  compliance (合规)    -> Qwen3.8-Max  ~ 0.038 yuan/call",
        "",
        "月度预估 (日均200次: 80%standard + 15%simple + 5%complex):",
    ]

    monthly_smart = (200 * 0.80 * 0.0004 + 200 * 0.15 * 0.0001 + 200 * 0.05 * 0.005) * 30
    monthly_bailian = 200 * 0.0378 * 30
    lines.append("  智能路由: %.2f yuan/month" % monthly_smart)
    lines.append("  全用百炼: %.2f yuan/month (贵 %.0f 倍)" % (monthly_bailian, monthly_bailian / monthly_smart))

    return "\n".join(lines)
