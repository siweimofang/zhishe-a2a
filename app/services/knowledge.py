"""
知识库 V0.1 (2026-06-13,V1.0 简化版)

项目书 Day 4 必交付。V0.1 用 JSON 存,等 V1.5 真接 RAG 时升级到 pgvector。

知识库分类(项目书原话,共 100 条):
1. 沈阳装修价格基准 (20 条)
2. 沈阳装修流程与规定 (15 条)
3. 沈阳主流建材市场与价格 (15 条)
4. 沈阳装修避坑指南 (20 条)
5. 沈阳装修风格流行趋势 (15 条)
6. 装修常见问题解答 (15 条)

V0.1 先做 20 条覆盖前 4 类,V1.5 补到 100 条。
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

import jieba

# 启动即预载词典,避免服务重启后首个请求多等0.6秒(2026-08-11)
jieba.initialize()

log = logging.getLogger("knowledge")

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "knowledge.json"

# 原文库:《选择、价值与决策》全书原文按批次切块(2026-08-11)
# 扫描识别原文,含OCR错字,引用时须标注"原文引用,个别字词可能因识别有误"
SRC_FILE = Path(__file__).parent.parent.parent / "data" / "knowledge_src_cvf.json"


def _load_kb() -> list[dict]:
    """读知识库(每次重读,允许热加载)"""
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_src() -> list[dict]:
    """读原文库(每次重读,允许热加载):《选择、价值与决策》全书原文块"""
    if not SRC_FILE.exists():
        return []
    try:
        with open(SRC_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log.warning("原文库加载失败: %s", SRC_FILE)
        return []


# 行业词表补强:行业习惯说法,保证 jieba 未收录时也能命中(2026-08-11)
INDUSTRY_KW = frozenset([
    u"沈阳", u"半包", u"大包", u"全包", u"全案", u"报价", u"价格", u"装修", u"户型", u"风格",
    u"水电", u"瓦工", u"木工", u"油漆", u"防水", u"拆改", u"流程", u"避坑", u"材料", u"辅材",
    u"主材", u"经济", u"中端", u"高端", u"豪华", u"平米", u"平方米", u"全屋定制", u"量房",
    u"装修公司", u"设计师", u"环保", u"甲醛", u"工期", u"施工", u"工艺",
    u"建材", u"市场", u"瓷砖", u"板材",
    # 墙面篇补强(2026-08-11):jieba切分失败需整词匹配
    u"硬包", u"木饰面", u"灰镜", u"卡式龙骨",
    # 材料收口篇补强(2026-08-12):jieba切分失败需整词匹配
    u"内凹",
    # 常用节点篇补强(2026-08-12):英文缩写被中文正则剔除需整词匹配
    u"GRG", u"GRC",
    # 100个节点篇补强(2026-08-12):jieba切成单字需整词匹配
    u"斜撑",
    # 软装风格篇补强(2026-08-12):jieba错切"新古典"为"古典家具"、"软装要"吞"软装"需整词匹配
    u"新古典", u"软装",
    # 软装风格批次2补强(2026-08-12):jieba切"老家具"为"老"+"家具"丢核心词需整词匹配
    u"老家具",
    # 软装风格批次3补强(2026-08-12):jieba未收录"侘寂"切成单字剔除、"和纸灯"错切为"纸灯"需整词匹配
    u"侘寂", u"和纸",
    # 谈单话术补强(2026-08-12):jieba把"商量"切成单字剔除导致查询关键词清空需整词匹配
    u"商量",
    # 软装搭配批次2补强(2026-08-12):英文缩写被中文正则剔除需整词匹配
    u"L型", u"U型", u"I型", u"Z形",
    # 软装搭配批次2补强(2026-08-12):jieba错切"边几"为"边"+"几"丢核心词需整词匹配
    u"边几",
    # 软装搭配批次3补强(2026-08-12):jieba错切"线吊/链吊"为单字或合词"吊好"需整词匹配
    u"线吊", u"链吊", u"管吊",
    # 软装搭配批次5补强(2026-08-13):jieba错切"飘窗"为"飘/窗用"、"抱枕"切单字"抱/枕"、"撞色"错切为"用撞色"需整词匹配
    u"飘窗", u"抱枕", u"撞色",
    # 软装搭配批次6补强(2026-08-14):jieba错切"格栅"为"格栅有"丢核心词;"什么花"类问法单字"花"被剔除只剩场景词(玄关/卧室)同分垫底需整词匹配
    u"格栅", u"什么花",
    # 施工工艺遗留5条修复(2026-08-14):jieba切单字剔除致同分平票垫底需整词匹配
    # k530钢柱干挂: "钢柱/抱箍"切单字; k584地毯铺贴: "压边条"切"压边/条";
    # k909钢梯踏步: "钢楼梯"丢"钢"字、"踏步灯"切"踏步"; k911玻璃栏板: "遮光膜/调节螺栓"切单字
    u"钢柱", u"抱箍", u"压边条", u"钢楼梯", u"踏步灯", u"遮光膜", u"调节螺栓",
    # k584地毯铺贴修复补充(2026-08-14): jieba切"铺贴"为单字剔除致"地毯怎么铺贴施工"类问法丢核心词
    u"铺贴",
    # 设计心理k1478修复(2026-08-14): "说明"在WEAK_KW弱词表被剔除,致"为什么给客户发的说明看了不懂"
    # 类问法词集清空返回空;补强后词集={说明},k1478/k1532同分3按库序k1478在前命中
    u"说明",
    # k584二次修复(2026-08-14): "铺地毯收口怎么处理"类问法"铺"被jieba切单字剔除,
    # 词集只剩{地毯,收口}10分输给k568/k580/k591(收口条t2 12分);补整词后k584 question命中+3达13分
    u"铺地毯",
    # k1280沙发座高修复(2026-08-14): "座高"被jieba切"座/高"单字剔除,变体"沙发座高多少合适"
    # 词集只剩{沙发,合适}与k1279同分垫底;补整词后k1280 question/tags/answer全命中+6达12分
    u"座高",
    # k1567上翻门修复(2026-08-14): "上翻门"被jieba切单字剔除,变体"上翻门还是平开门好"
    # 词集只剩{平开门}输给其它柜门条目;补整词后k1567 question命中+6
    u"上翻门",
    # 住宅空间设计k1640修复(2026-08-14): "雨搭"被jieba切单字"雨/搭"剔除,变体"窗户上面做多宽的雨搭"
    # 词集只剩{窗户,多宽}输给其它窗户条目;补整词后k1640 question命中+3
    u"雨搭",
    # 住宅空间设计k1652/k1657修复(2026-08-14): "朝北"被jieba切单字"朝/北"剔除致
    # "房子朝北采光差怎么办"词集只剩{房子,采光}输给补词后的k1653;"对着"切单字"对/着"剔除致
    # "卧室门对着客厅好吗"词集只剩泛化词{卧室,客厅}全输给软装12分条目;补整词后两条目question命中+3
    u"朝北", u"对着",
])


def search(query: str, top_k: int = 3) -> list[dict]:
    """
    知识库关键词搜索 V0.2 (2026-08-11)
    - jieba分词实义词为核心词(剔除口语虚词),行业词表补强
    - 加权:question命中3分 / tags命中2分 / answer命中1分
    - 无实义词命中时返回空(宁缺毋滥)

    修复背景:V0.1 把整句连续中文当单个关键词,长句几乎匹配不上,
    实际只剩预置词表生效,同分条目按库内顺序返回(新条目永远排不进)。
    """
    kb = _load_kb()
    if not kb or not query:
        return []

    keywords = set(_segment(query))
    for word in INDUSTRY_KW:
        if word in query:
            keywords.add(word)
    if not keywords:
        return []

    scored = []
    for entry in kb:
        q = entry.get("question", "")
        a = entry.get("answer", "")
        t = " ".join(entry.get("tags", []))
        score = 0
        for kw in keywords:
            if kw in q:
                score += 3
            if kw in t:
                score += 2
            if kw in a:
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:top_k]]


def format_for_llm(results: list[dict]) -> str:
    """把搜索结果格式化成可注入 LLM 的知识块"""
    if not results:
        return ""
    lines = ["[相关知识库条目 - V0.1 知识库,2026-06-13]"]
    for i, e in enumerate(results, 1):
        lines.append(f"\n## {i}. {e['question']}")
        lines.append(f"分类:{e.get('category', '未分类')}")
        lines.append(f"\n{e['answer']}")
    return "\n".join(lines)


def _extract_kw(text: str) -> set:
    """从查询中提取中文关键词:每个2字以上中文段拆成2-5字滑动窗口子串"""
    kws = set()
    for seg in re.findall(r'[\u4e00-\u9fff]{2,}', text):
        n = len(seg)
        for i in range(n):
            for j in range(i + 2, min(i + 6, n) + 1):
                kws.add(seg[i:j])
    return kws


# 口语虚词:无检索信息量,仅命中这些词的查询不做原文匹配(宁缺毋滥)
WEAK_KW = frozenset([
    u"怎么", u"什么", u"为什么", u"比较", u"时候", u"客户", u"合理", u"应该",
    u"觉得", u"考虑", u"问题", u"可以", u"希望", u"担心", u"一直", u"总是",
    u"真的", u"多少", u"大概", u"咱们", u"我们", u"自己", u"一下", u"一些",
    u"情况", u"感觉", u"看法", u"意见", u"想法", u"决定", u"处理", u"了解",
    u"解释", u"推荐", u"建议", u"说明", u"讨论", u"商量", u"确认", u"需要",
    u"知道", u"明白", u"想要", u"是否", u"如何", u"哪里", u"哪个", u"哪些",
    u"是不是", u"能不能", u"要不要", u"会不会", u"可不可以", u"该不该", u"应不应该",
    u"到底", u"究竟", u"为啥",
    u"一般", u"通常", u"平时", u"日常", u"大家", u"这种", u"那种", u"这样",
    u"那样", u"来说", u"来说", u"来讲", u"而言", u"来讲", u"先生", u"女士",
    u"下来", u"愿意", u"拖着", u"不定", u"省下",
    u"还是",
])

# 标题中带章节号的正则(平票时优先返回正文章节,避免命中封面/序言块)
_CHAPTER_RE = re.compile(u"第\\s*[0-9一二三四五六七八九十百零两]+\\s*章")


def _segment(text: str) -> list[str]:
    """jieba分词,只保留2字以上中文实义词(剔除口语虚词)"""
    words = []
    for w in jieba.lcut(text):
        w = w.strip()
        if len(w) < 2:
            continue
        if not re.fullmatch(r"[\u4e00-\u9fff]+", w):
            continue
        if w in WEAK_KW:
            continue
        words.append(w)
    return words


def _src_score_blocks(query: str) -> list[tuple]:
    """
    原文块打分:返回 [(score, core_count, blk)] 按相关度降序
    - 核心词 = jieba分词得到的实义词(标题命中×6, 正文命中×3)
    - 加成词 = 滑动窗口子串(命中×1),只锦上添花,不能单独支撑命中
    - 块有效条件:至少1个核心词命中(宁缺毋滥)
    - 平票时:核心词多者优先 → 正文章节优先 → 块序号小者优先
    """
    src = _load_src()
    if not src or not query:
        return []

    core = set(_segment(query))
    if not core:
        return []

    bonus = _extract_kw(query) - WEAK_KW - core

    rows = []
    for idx, blk in enumerate(src):
        title = blk.get("title", "")
        content = blk.get("content", "")
        core_title = {k for k in core if k in title}
        core_content = {k for k in core if k in content}
        if not core_title and not core_content:
            continue
        score = len(core_title) * 6 + len(core_content) * 3
        for k in bonus:
            if k in title or k in content:
                score += 1
        core_count = len(core_title) + len(core_content)
        has_chapter = bool(_CHAPTER_RE.search(title))
        rows.append((score, core_count, has_chapter, idx, blk))

    rows.sort(key=lambda x: (-x[0], -x[1], not x[2], x[3]))
    return [(score, count, blk) for score, count, _, _, blk in rows]


def search_src(query: str, top_k: int = 1) -> list[dict]:
    """
    原文库搜索 V0.2 (2026-08-11)
    - 核心词:jieba分词实义词,标题命中6分/正文命中3分
    - 滑动窗口子串只做辅助加分,不能单独支撑命中(避免句式碎片刷分)
    - 无实义词命中时返回空(宁缺毋滥,知识库条目层兜底)
    """
    rows = _src_score_blocks(query)
    return [blk for _, _, blk in rows[:top_k]]


def format_src_for_llm(results: list[dict]) -> str:
    """把原文块格式化成可注入 LLM 的参考原文块(标注出处,提示OCR识别误差)"""
    if not results:
        return ""
    lines = ["[参考原文 - 《选择、价值与决策》全书原文,2026-08-11]",
             "注:原文为扫描识别,个别字词可能有误,引用时留意。"]
    for i, e in enumerate(results, 1):
        lines.append(f"\n## {i}. 原文出处:{e.get('title', '未知')}")
        lines.append(e.get("content", ""))
    return "\n".join(lines)


# ============================================================
# 单元测试入口
# ============================================================

if __name__ == "__main__":
    tests = [
        "沈阳 90 平半包大概多少钱?",
        "装修怎么避坑?",
        "沈阳哪里买建材?",
        "水电改造要注意什么?",
    ]
    for q in tests:
        print(f"\n=== Query: {q} ===")
        results = search(q, top_k=2)
        for r in results:
            print(f"  [{r.get('category')}] {r['question'][:50]}")
