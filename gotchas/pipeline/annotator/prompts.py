"""
提示词模板：指导 DeepSeek 从经验素材中抽取结构化 KU。

设计要点：
- 只让模型产出"内容字段"，ku_id 与 metadata 由 validator 统一补（防 AI 乱编号）。
- 把全部枚举白名单内嵌进提示词，约束模型只选合法值。
- 强制只返回 JSON 数组，便于解析。
"""

# 枚举白名单（与 taxonomy_v1.json 一致，内嵌以降低模型越界概率）
_ENUM_HINT = """
【极其重要】所有枚举字段只填英文代码本身（例如 stage 填 "STAGE_04"、trade 填 "TRADE_TILE"），
严禁把后面的中文说明一起填进去（不要写成 "STAGE_04施工阶段"）。括号内中文仅供你理解含义。

【可选枚举值，必须严格从中选取】
stage（单选）: STAGE_01前期准备 / STAGE_02设计阶段 / STAGE_03报价签约 / STAGE_04施工阶段 / STAGE_05主材安装 / STAGE_06软装进场 / STAGE_07验收交付 / STAGE_08售后维保
role（多选）: ROLE_OWNER业主 / ROLE_DESIGNER设计师 / ROLE_CONTRACTOR施工方 / ROLE_INDUSTRY行业
severity（单选）: SEV_CRITICAL致命(>2万) / SEV_HIGH高危(5千-2万) / SEV_MEDIUM中危(1千-5千) / SEV_LOW低危(<1千)
problem_type（多选）: TYPE_FRAUD欺诈套路 / TYPE_QUALITY质量问题 / TYPE_OMISSION漏项遗漏 / TYPE_DELAY延期拖延 / TYPE_COST费用争议 / TYPE_COMMUNICATION沟通问题
trade（多选）: TRADE_DESIGN设计 / TRADE_DEMOLISH拆改 / TRADE_PLUMBING水电 / TRADE_WATERPROOF防水 / TRADE_TILE瓦工瓷砖 / TRADE_CARPENTRY木工 / TRADE_PAINT油工涂料 / TRADE_CABINET橱柜定制 / TRADE_DOOR门窗 / TRADE_FLOOR地板 / TRADE_BATHROOM卫浴 / TRADE_ELECTRICAL电气智能家居
material（多选）: MAT_PIPE水管管件 / MAT_WIRE电线线管 / MAT_CEMENT水泥砂浆 / MAT_TILE瓷砖石材 / MAT_PAINT涂料乳胶漆 / MAT_BOARD板材木制品 / MAT_GLUE胶粘剂密封胶 / MAT_HARDWARE五金件 / MAT_APPLIANCE家电设备 / MAT_FURNITURE家具软装 / 无则填 []
scope（单选）: universal全国通用 / regional:shenyang沈阳特化 / regional:north北方通用 / regional:south南方通用 / regional:other其他地域
evidence.source_type（单选）: official_report / legal_case / consumer_complaint / industry_standard / expert_opinion / user_feedback / media_report
evidence.confidence（单选）: 高(多源验证) / 中(单源可靠) / 低(待验证)
evidence.frequency（单选，可选）: 极高频(>60%) / 高频(30-60%) / 中频(10-30%) / 低频(<10%)
"""

SYSTEM_PROMPT = """你是装修行业知识工程师，负责把资深设计师的实战经验提炼成结构化"知识单元(KU)"。
你的产出将进入知设 Gotchas 库，用于帮业主避坑。务必：
1. 一条素材里若含多个独立坑点，拆成多条 KU。
2. 只输出真正"不说就踩坑"的经验，参考性数据（如单纯价格表）不要产出。
3. description 和 how_to_avoid 各 50-500 字，how_to_avoid 必须可操作（分步骤）。
4. 严格使用给定枚举值，不得自创。
5. 只返回 JSON 数组，不要任何解释文字、不要 markdown 代码块标记。"""


def build_user_prompt(material_text: str) -> str:
    """构造用户提示词。"""
    return f"""{_ENUM_HINT}

【输出 JSON 数组，每个元素是一条 KU，字段如下】
[
  {{
    "title": "20字以内点明坑点",
    "stage": "STAGE_XX",
    "role": ["ROLE_XX"],
    "severity": "SEV_XX",
    "problem_type": ["TYPE_XX"],
    "trade": ["TRADE_XX"],
    "material": ["MAT_XX"],
    "scope": "universal",
    "description": "50-500字，说清这个坑是什么、为什么坑、损失量级",
    "typical_scenario": "300字以内，一个真实感的具体场景案例",
    "how_to_avoid": "50-500字，分步骤的可操作避坑方法",
    "evidence": {{
      "source_type": "expert_opinion",
      "source_ref": "设计师实战经验",
      "frequency": "高频(30-60%)",
      "confidence": "中(单源可靠)"
    }},
    "causal_chain": {{
      "root_cause": "根本原因",
      "direct_cause": "直接原因",
      "consequence": "后果"
    }}
  }}
]

【待提炼的经验素材】
{material_text}

现在只输出 JSON 数组："""
