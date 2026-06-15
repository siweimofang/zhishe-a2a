# 知设未选 DeepSeek 情况说明 V0.1

> 编写日期: 2026-06-16
> 编写人: Mavis(mavis-agent)
> 用途: 战略归档,记录"为什么没选 DeepSeek"和"什么情况下可以重启"

---

## 一、平台基本信息
- 平台名: DeepSeek
- 母公司: 幻方量化(High-Flyer)
- 主对话 LLM: DeepSeek-V4-Pro
- 智能体平台名: ❌ **没有**(2026-06-16 用户实查)
- URL: https://api-docs.deepseek.com

## 二、第三方 Agent 入驻支持(沙箱实查 2026-06-16)
- 是否支持第三方 Agent 入驻/上架: ❌ **没有**(DeepSeek 官方实答"目前 DeepSeek 官方服务不支持第三方 Agent 注册和自动调用")
- 主对话是否自动调第三方 Agent: ❌ **不支持**
- 入驻门槛(企业认证/资质要求): N/A
- 流量规模: API 开放,无平台

## 三、未选原因
1. DeepSeek 是**模型公司**不是**应用平台**,**没有"智能体平台"等价的"千问智能体广场"**
2. 只能通过 API 自建,**无 Agent 入驻入口**
3. API 已通过 zhishe-a2a 内壳 LLM 形式使用(DeepSeek-v4-pro 当前是内壳 LLM 之一)

## 四、未来重启条件
满足以下**任一**条件可重启该项目:
- 条件 1: DeepSeek 上线"智能体广场"或类似"千问智能体广场"的第三方 Agent 平台
- 条件 2: DeepSeek 公布"品牌 Agent 入驻"政策(类似千问 2026-06-03 新政)
- 条件 3: DeepSeek 主对话支持"自动 dispatch 第三方 Agent"

## 五、相关事实链(沙箱验证)
用户 2026-06-16 实查 DeepSeek-V4-Pro,原文引用:
"DeepSeek-V4-Pro(即我)并不支持在对话中主动调用第三方 Agent 开发者提供的垂直领域 Agent"

补充事实(出处同上):
- DeepSeek 官方明确回复"目前 DeepSeek 官方服务不支持第三方 Agent 注册和自动调用"
- DeepSeek 公开渠道仅有 API 文档(https://api-docs.deepseek.com),未见任何 Agent 广场/Agent Store 类入口
- zhishe-a2a 项目中,DeepSeek-V4-Pro 已作为内壳 LLM 选项之一存在(详见 Project Context 中 LLM 路由配置),其角色是"被调用的模型"而非"承载 Agent 的平台"

结论:DeepSeek 在当前生态位下与 zhishe-a2a 的"借平台流量分发"诉求不匹配 —— 它是上游模型供应商,不是下游 Agent 分发平台,因此归档为"未选 + 短期内无重启必要"。

## 六、归档摘要(便于跨文档比对)

| 维度 | DeepSeek 现状 | zhishe-a2a 诉求 | 匹配度 |
|------|--------------|----------------|--------|
| 平台形态 | 模型公司(API 开放) | 应用平台 + Agent 分发 | ❌ 不匹配 |
| 第三方 Agent 入驻 | 无 | 必须有 | ❌ 缺 |
| 主对话自动调第三方 | 无 | 强烈需要(V1.0 千问版核心红利) | ❌ 缺 |
| 当前在 zhishe-a2a 中的角色 | 内壳 LLM 之一(被调用方) | 外部分发平台(承载方) | 角色错位 |
| 重启概率 | 极低(需 DeepSeek 战略转向 Agent 平台) | — | — |

跨文档归档标签:`#模型公司` `#无Agent平台` `#API-only` `#重启条件:平台化转型`

备注:与 Kimi 归档文档同属"模型公司无 Agent 平台"类别,两份文档可对照阅读。若 DeepSeek 与 Kimi 任一启动 Agent 平台战略,可同步重启本归档。

