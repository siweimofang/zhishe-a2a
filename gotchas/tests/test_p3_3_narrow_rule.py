"""P3-3 F5-1 窄规则校验器测试。

验收标准:
1. question 长度 >= 8 字
2. question 不含宽泛词表(BROAD_KEYWORDS)中的词
违规返回错误字符串,不加入缓存。
"""
import sys
sys.path.insert(0, r"D:\知设Agent生态\千问AI Agent\zhishe-a2a")

from gotchas.runtime.rule_manager import RuleManager, EffectRegistry, validate_narrow_rule, BROAD_KEYWORDS

def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  [通过] {name}")
    else:
        print(f"  [失败] {name} -- {detail}")
        raise AssertionError(f"FAIL: {name}: {detail}")


# ── 测试 1: validate_narrow_rule 直接测试 ──
print("== 测试 1: validate_narrow_rule 直接调用 ==")

# 正常 rule -> None
ok_rule = {"question": "装修时吊顶高度一般多少合适？", "title": "吊顶高度问题"}
err = validate_narrow_rule(ok_rule)
check("正常 question 无错误", err is None, f"返回:{err}")

# 过短 question (<8 字)
short_rule = {"question": "吊顶多高好？", "title": ""}
err = validate_narrow_rule(short_rule)
check("过短 question 被拦截", "过短" in str(err), f"返回:{err}")

# 含宽泛词「注意」
broad_note = {"question": "装修时要注意什么？", "title": ""}
err = validate_narrow_rule(broad_note)
check("含宽泛词'注意'被拦截", "注意" in str(err), f"返回:{err}")

# 含宽泛词「安全」（确保不含注意）
broad_safe = {"question": "施工现场有哪些安全保护要求", "title": ""}
err = validate_narrow_rule(broad_safe)
check("含宽泛词'安全'被拦截", "安全" in str(err), f"返回:{err}")

# 含宽泛词「必须」（不含注意的词）
broad_must = {"question": "装修必须要做的事", "title": ""}
err = validate_narrow_rule(broad_must)
check("含宽泛词'必须'被拦截", "必须" in str(err) or "注意" in str(err), f"返回:{err}")

# 含宽泛词「应该」（不含其他宽泛词）
broad_should = {"question": "水电改造应该如何规划施工", "title": ""}
err = validate_narrow_rule(broad_should)
check("含宽泛词'应该'被拦截", "应该" in str(err), f"返回:{err}")

# 含宽泛词「小心」（不含其他宽泛词）
broad_careful = {"question": "防水施工要小心漏水的问题吗", "title": ""}
err = validate_narrow_rule(broad_careful)
check("含宽泛词'小心'被拦截", "小心" in str(err), f"返回:{err}")

# 空 question
empty_q = {"question": "", "title": ""}
err = validate_narrow_rule(empty_q)
check("空 question 被拦截", "为空" in str(err), f"返回:{err}")

# 有 title 但无 question (用 title 作为 fallback)
ok_title = {"question": "", "title": "室内装修中水电改造的规范流程和要求是什么？"}
err = validate_narrow_rule(ok_title)
check("title 作为 fallback 正常通过", err is None, f"返回:{err}")

print("\n== 测试 2: RuleManager.add_rule 集成窄规则校验 ==")

class FakeMarkDirty:
    def __call__(self): pass

rm = RuleManager([], {}, registry=EffectRegistry(), mark_dirty=FakeMarkDirty())

# 正常规则可以添加
valid_ku = {
    "ku_id": "NARROW-VALID-001",
    "question": "装修时吊顶高度一般多少合适？",
    "answer": "吊柜高度通常在60-70cm之间",
    "category": "kitchen",
}
try:
    eff = rm.add_rule(valid_ku)
    check("正常规则可成功添加", True, "")
except ValueError as e:
    check("正常规则可成功添加", False, str(e))

# 过短规则拒绝
short_ku = {
    "ku_id": "NARROW-SHORT-001",
    "question": "吊顶多高好？",
}
try:
    rm.add_rule(short_ku)
    check("过短规则被拒绝", False, "未抛出异常")
except ValueError as e:
    check(f"过短规则拒绝: {str(e)[:50]}", "过短" in str(e), str(e))

# 含宽泛词「注意」拒绝
broad_ku = {
    "ku_id": "NARROW-BROAD-001",
    "question": "装修时要注意什么？",
}
try:
    rm.add_rule(broad_ku)
    check("含宽泛词规则被拒绝", False, "未抛出异常")
except ValueError as e:
    check(f"含宽泛词规则拒绝: {str(e)[:50]}", "宽泛词" in str(e) or "注意" in str(e), str(e))

print("\n" + "=" * 60)
print(f"P3-3 窄规则校验器测试完成!")
