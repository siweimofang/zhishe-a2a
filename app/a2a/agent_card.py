"""
AgentCard 构造
千问通过 GET /.well-known/agent.json 发现 Agent 能力
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
            "沈阳本地化装修报价专家。"
            "覆盖报价参考、避坑指南、流程答疑、行情问答。"
            "不提供具体承诺价,建议实地量房。"
        ),
        url=f"{base_url}/a2a",
        version="1.0.0",
        protocolVersion="0.2.5",
        capabilities=AgentCapabilities(streaming=False),
        security=["apiKey"],
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        skills=[
            AgentSkill(
                id="shenyang-renovation-quote",
                name="沈阳装修报价参考",
                description=(
                    "根据用户提供的面积/户型/档次/装修方式/风格,"
                    "给出沈阳市场参考价区间(low/median/high),"
                    "并附 5 大项分项与免责说明。"
                ),
                tags=["装修", "报价", "沈阳", "renovation", "quote"],
                examples=[
                    "我家 90 平三室,想半包,大概多少钱?",
                    "100 平全包中档现代简约,沈阳大概多少?",
                ],
            ),
            AgentSkill(
                id="renovation-pitfall-advice",
                name="装修避坑指南",
                description=(
                    "针对装修过程中常见的报价陷阱、增项预警、"
                    "合同要点等,给出本地化避坑建议。"
                ),
                tags=["装修", "避坑", "沈阳", "renovation", "tips"],
                examples=[
                    "装修最容易踩的坑是什么?",
                    "半包装修要注意什么?",
                ],
            ),
            AgentSkill(
                id="renovation-process",
                name="装修流程答疑",
                description=(
                    "解答装修流程相关问题:开工准备、"
                    "水电木瓦油各阶段、验收节点等。"
                ),
                tags=["装修", "流程", "renovation", "process"],
                examples=[
                    "装修一般要多长时间?",
                    "水电改造需要注意什么?",
                ],
            ),
        ],
    )
