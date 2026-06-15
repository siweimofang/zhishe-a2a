# 知设未选 Kimi 情况说明 V0.1

> 编写日期: 2026-06-16
> 编写人: Mavis(mavis-agent)
> 用途: 战略归档,记录"为什么没选 Kimi(月之暗面)"和"什么情况下可以重启"

---

## 一、平台基本信息
- 平台名: Kimi(月之暗面)
- 母公司: Moonshot AI
- 主对话 LLM: Kimi K2.5/K2.6
- 智能体平台名: ❌ **不支持**(2026-06-16 用户实查)
- URL: https://platform.moonshot.cn

## 二、第三方 Agent 入驻支持(沙箱实查 2026-06-16)
- 是否支持第三方 Agent 入驻/上架: ❌ **不支持**
- 主对话是否自动调第三方 Agent: ❌ **不支持**
- 入驻门槛(企业认证/资质要求): N/A
- 流量规模: Function Calling 自建可用,无平台

## 三、未选原因
1. Moonshot AI **目前聚焦模型能力 + C 端产品体验**,**暂未公布第三方 Agent 生态平台计划**
2. 跟 DeepSeek 一样,只能通过 Function Calling 自建
3. Function Calling 自建路径**没"主对话自动调"红利**,跟 V1.3 小艺 / V1.4 智谱没法比

## 四、未来重启条件
满足以下**任一**条件可重启该项目:
- 条件 1: Moonshot AI 上线"智能体广场"或类似平台
- 条件 2: Moonshot AI 公布"品牌 Agent 入驻"政策
- 条件 3: Kimi 主对话支持"自动 dispatch 第三方 Agent"

## 五、相关事实链(沙箱验证)
用户 2026-06-16 实查 Moonshot AI 开放平台,原文引用:
- "Kimi 目前不支持直接对第三方 Agent 开发者开放这种调用机制"
- "Moonshot AI(月之暗面)主要聚焦于模型能力本身和 C 端产品体验,暂未公布类似 GPTs Store 或第三方 Agent 生态平台的计划"

补充事实(出处同上):
- Moonshot AI 公开渠道仅有 platform.moonshot.cn 的 API 文档,未见 Agent 广场/Agent Store 类入口,与 DeepSeek 同属"模型公司"生态位
- Function Calling 接口(K2.5/K2.6)可用,但属于"开发者自建"路径,需要用户主动访问 Kimi 页面 + 触发工具调用,**没有"主对话场景内自动分发"的红利**
- Project Context 中 V1.3(华为小艺)/ V1.4(智谱)的核心价值是"主对话自动 dispatch 第三方 Agent",Kimi 在该维度无对标能力
- Kimi 自身的用户体量集中在 C 端长文档阅读/资料整理场景,与装修垂类咨询用户重合度低

结论:Kimi 与 DeepSeek 同属"模型供应商而非 Agent 分发平台",自建路径无平台流量加持,且与 zhishe-a2a 的"借主对话分发"核心打法不匹配,因此归档为"未选 + 与 DeepSeek 同类,任一重启即可通用"。

## 六、归档摘要(便于跨文档比对)

| 维度 | Kimi 现状 | zhishe-a2a 诉求 | 匹配度 |
|------|----------|----------------|--------|
| 平台形态 | 模型公司 + C 端产品 | 应用平台 + Agent 分发 | ❌ 不匹配 |
| 第三方 Agent 入驻 | 无 | 必须有 | ❌ 缺 |
| 主对话自动调第三方 | 无(Function Calling 仅自建) | 强烈需要(V1.0 千问版核心红利) | ❌ 缺 |
| 与 DeepSeek 差异 | 用户场景偏长文档/资料整理 | 装修垂类咨询 | 与垂类不重合 |
| 在 zhishe-a2a 中的潜在角色 | 仅可作内壳 LLM(未启用) | 外部分发平台 | 角色错位 |
| 重启概率 | 极低(需 Moonshot AI 战略转向 Agent 生态) | — | — |

跨文档归档标签:`#模型公司` `#无Agent平台` `#Function-Calling-only` `#与DeepSeek同类`

