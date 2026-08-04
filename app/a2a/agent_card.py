"""
AgentCard 构造
千问/小艺/HarmonyOS 7 通过 GET /.well-known/agent.json 发现 Agent 能力
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str]
    examples: Optional[List[str]] = None
    inputModes: Optional[List[str]] = None
    outputModes: Optional[List[str]] = None


class AgentCapabilities(BaseModel):
    streaming: bool = False
    extensions: Optional[List[Dict[str, Any]]] = None


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str
    protocolVersion: str
    capabilities: AgentCapabilities
    security: Optional[List[str]] = None
    defaultInputModes: List[str]
    defaultOutputModes: List[str]
    skills: List[AgentSkill]


def get_agent_card(base_url: str = "https://example.com") -> AgentCard:
    """生成 AgentCard(URL 由部署时配置)"""
    return AgentCard(
        name="知设AI装修顾问",
        description=(
            "装修 AI 顾问,提供报价、施工标准、设计方案、建材品牌的咨询,助你避坑。"
            "基于装修行业多年实战经验,不提供具体承诺价,建议实地量房。"
            "本智能体为任务型工具智能体(AI 咨询助手),非持证监理/设计师/施工企业,"
            "不提供需要法定资质的鉴定与验收结论;信息仅供参考,以实际勘察和合同为准。"
        ),
        url=f"{base_url}/a2a",
        version="1.4.0",
        protocolVersion="0.2.5",
        capabilities=AgentCapabilities(streaming=True),  # V1.3.1:后端 openai_compat.py 早已支持 SSE,此处开启让客户端知道(V1.4 准备)
        security=["apiKey"],
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        skills=[
            AgentSkill(
                id="renovation_quote",
                name="装修报价咨询",
                description=(
                    "装修报价、预算估算、价格查询、费用计算、多少钱一平、"
                    "硬装报价、软装预算、半包大包报价。"
                    "根据用户提供的城市/面积/户型/档次,给出市场参考价区间"
                    "(经济型/中档/中高档/豪华),并附 5 大项分项与免责说明。"
                ),
                tags=["装修", "报价", "renovation", "quote", "家装", "预算",
                      "半包", "大包", "全案", "平米单价"],
                examples=[
                    "我家 90 平三室,想半包,大概多少钱?",
                    "100 平全包中档现代简约,大概多少?",
                    "80 平两室一厅简装预算明细",
                    "沈阳浑南装修多少钱一平?",
                ],
            ),
            AgentSkill(
                id="construction_standard",
                name="施工标准咨询",
                description=(
                    "施工工艺、施工流程、装修步骤、施工标准、验收标准、"
                    "隐蔽工程、防水、国标、监理。"
                    "水电改造、防水、墙面、地面等隐蔽工程和面子工程的"
                    "施工标准与验收规范。"
                ),
                tags=["施工", "标准", "construction", "验收", "水电", "防水",
                      "国标", "GB 50327", "GB 50150", "GB 50210"],
                examples=[
                    "水电改造要注意什么?",
                    "防水怎么做才算合格?",
                    "墙面刷漆的标准工序是什么?",
                    "GB 50327 试压标准是多少?",
                ],
            ),
            AgentSkill(
                id="design_scheme",
                name="设计方案咨询",
                description=(
                    "户型分析、空间改造、房间布局、拆墙改墙、户型优化、"
                    "动线设计、风格搭配。"
                ),
                tags=["设计", "方案", "design", "户型", "风格", "动线",
                      "拆改", "空间规划"],
                examples=[
                    "小户型怎么设计显大?",
                    "客厅和阳台要不要打通?",
                    "日式风格和新中式怎么选?",
                    "承重墙能拆吗?",
                ],
            ),
            AgentSkill(
                id="building_material_brand",
                name="建材品牌咨询",
                description=(
                    "装修材料品牌、建材市场、家具品牌、瓷砖地板、卫浴品牌、"
                    "油漆涂料、品牌对比。"
                    "主材、辅材、家具、家电的品牌对比与选购建议。"
                ),
                tags=["建材", "品牌", "material", "brand", "主材", "辅材",
                      "瓷砖", "地板", "卫浴", "乳胶漆"],
                examples=[
                    "乳胶漆什么牌子好?",
                    "瓷砖选哪个品牌?",
                    "全屋定制选哪家?",
                    "伟星水管真假怎么看?",
                ],
            ),
            AgentSkill(
                id="renovation_pitfall",
                name="装修避坑指南",
                description=(
                    "装修避坑、装修陷阱、装修经验、过来人经验、施工猫腻、"
                    "增项漏项、低开高走。"
                    "针对装修过程中常见的报价陷阱、增项预警、"
                    "合同要点、偷工减料识别等,给出本地化避坑建议。"
                ),
                tags=["装修", "避坑", "renovation", "tips", "增项", "陷阱",
                      "猫腻", "过来人"],
                examples=[
                    "装修最容易踩的坑是什么?",
                    "半包装修要注意什么?",
                    "怎么判断装修公司是不是坑?",
                    "装修增项怎么防?",
                ],
            ),
        ],
    )
