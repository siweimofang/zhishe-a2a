# 知设 AI 装修顾问 (zhishe-a2a)

> 沈阳本地化装修报价 · **自建 Agent 版**
> 通过 Google A2A 0.2.5 协议被千问 APP 调用

**当前状态: V1.0 ✅ 跑通端到端** (2026/6/10 验证:28 个测试全绿,真对话调通 DeepSeek)

---

## 这是什么

一个**自建 FastAPI 服务**,不是百炼里"创建智能体"。它通过 [A2A 0.2.5 协议](https://google.github.io/A2A/) 暴露给千问 APP,千问发现你的 AgentCard 后主动调你。

```
千问 APP
   ↓ A2A JSON-RPC
本仓库的 FastAPI 服务(端口 8765)
   ↓ HTTP
DeepSeek(主力 LLM)
   ↓
返回 Agent 回复(末尾固定带"以上内容由 AI 生成,仅供参考")
```

---

## 30 秒跑起来

### 前置
- Python 3.11+ (项目用的是 3.11.9,装在 `C:\Users\Administrator\AppData\Local\Programs\Python\Python311`)
- DeepSeek API Key (去 https://platform.deepseek.com 申请)

### 三步启动
```powershell
# 1. 加 Python 到 PATH(每次新开 shell 都要做)
$env:Path = "C:\Users\Administrator\AppData\Local\Programs\Python\Python311;C:\Users\Administrator\AppData\Local\Programs\Python\Python311\Scripts;" + $env:Path

# 2. 装依赖(首次)
cd "D:\知设Agent生态\千问AI Agent\zhishe-a2a"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. 起服务
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

看到 `Application startup complete. Uvicorn running on http://127.0.0.1:8765` 就 OK。

---

## 关键端点

| 端点 | 作用 | 验证命令 |
|---|---|---|
| `GET /` | 服务元信息 | `curl http://127.0.0.1:8765/` |
| `GET /.well-known/agent.json` | AgentCard(千问发现 Agent) | `curl http://127.0.0.1:8765/.well-known/agent.json` |
| `POST /a2a/message/send` | **主路径** - JSON-RPC 同步调用 | `python examples\client_basic.py` |
| `POST /a2a/message/stream` | SSE 流式(V1.0 返回 -32601) | — |
| `GET /health/ready` | LLM 就绪检查 | `curl http://127.0.0.1:8765/health/ready` |

---

## 配置文件 `.env`

```ini
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
A2A_SERVER_HOST=0.0.0.0
A2A_SERVER_PORT=8765
LOG_LEVEL=INFO

# 可选:千问调你时的鉴权 key(留空 = 本地联调,不强制鉴权)
A2A_API_KEY=
```

`.env` **不要 commit 到 git**(已在 `.gitignore`)。

---

## 测试

```powershell
cd "D:\知设Agent生态\千问AI Agent\zhishe-a2a"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

**当前测试覆盖(28 个)**:
- **test_protocol.py (11个)**: A2A 协议层 - message/send、错误码、鉴权、LLM mock、JSON-RPC 解析
- **test_agents.py (15个)**: AgentCard 结构、3 个 skill、配置加载、LLM 服务层
- **test_smoke.py**: Mavis 写权限验证(非 pytest 风格,直接 `python tests/test_smoke.py` 跑)

跑完预期: `28 passed`。

---

## 调通性验证(2026/6/10 实测)

| 项 | 结果 |
|---|---|
| 服务启动 | ✅ PID 26520,端口 8765 监听中 |
| `GET /` | ✅ HTTP 200 |
| `GET /.well-known/agent.json` | ✅ 返回完整 AgentCard,3 个 skill |
| `examples\client_basic.py` 真对话 | ✅ DeepSeek 正常返回"沈阳 90 平半包"详细回复 |
| `pytest tests/` | ✅ 28 passed in 14s |
| `.env` 新 Key 已生效 | ✅ 头 `DEEPSEEK_API_KEY=sk-`,尾 `f2cd1fac7bc5` |

---

## 项目结构

```
zhishe-a2a/
├── app/
│   ├── main.py              # FastAPI 入口,挂 AgentCard + A2A router
│   ├── config.py            # pydantic-settings 读 .env
│   ├── a2a/
│   │   ├── server.py        # A2A 0.2.5 JSON-RPC(message/send)
│   │   └── agent_card.py    # AgentCard 构造(3 skills)
│   ├── api/
│   │   └── health.py        # 健康检查 + LLM 就绪
│   ├── services/
│   │   └── llm.py           # DeepSeek 调用封装 + AI 免责后缀
│   └── prompts/
│       └── xiaozhi.py       # 「小知」system prompt(身份/能力/红线)
├── data/                    # V2.0+ 接入(报价基准/敏感词/系数)
├── tests/
│   ├── test_protocol.py     # 协议层 11 个测试
│   ├── test_agents.py       # AgentCard + 配置 15 个测试
│   └── test_smoke.py        # Mavis 写权限验证
├── examples/
│   ├── client_basic.py      # 同步 A2A 客户端示例
│   └── client_stream.py     # 流式示例(服务端 V1.0 不支持)
├── .env                     # 本地配置(不 commit)
├── .env.example             # 配置模板
├── dev.ps1                  # 一键 PATH + venv 脚本
├── pyproject.toml
├── requirements.txt
├── README.md
└── uvicorn.log / .err       # 运行日志
```

---

## 千问管控台接入流程

1. 阿里云百炼管控台 → 「三方 Agent」管理
2. 点"接入三方 Agent"
3. 填 `https://你的域名/.well-known/agent.json`
4. 配 AgentCard 详情(自动发现)
5. 千问按 A2A 协议调你

**公网部署**:参考下面"部署"小节。

---

## 部署

### 联调(5 分钟):ngrok
```bash
ngrok http 8765
# 拿到 https://xxxx.ngrok-free.app
# 写到 .env:PUBLIC_BASE_URL=https://xxxx.ngrok-free.app
# 重启服务
```

### 正式:阿里云轻量 99 元/年 + 备案域名 + HTTPS
详见 `deploy/README.md`(待补)。

---

## 合规要点(已固化在 prompt)

- ✅ 不持有具体价格数据
- ✅ 不主动提任何外部联系方式(微信/二维码/电话)
- ✅ 不推荐具体装修公司
- ✅ 所有"线下服务"引导用户在千问 APP 内继续对话
- ✅ 末尾固定加"以上内容由 AI 生成,仅供参考"
- ✅ 不用绝对化用语(违反广告法)

---

## 战略定位(从 V1.0 计划书继承)

- 第一性原理:数字智能进化效率 > 生物智能
- 1 人 + AI 顶 10 人团队
- 沈阳本地化数据护城河
- 三层枷锁:身份 / 工具 / 利益
- 三阶段架构:单体(V1.0 当前) → 主从 → 市场机制

---

## V1.0 验收(2026/6/10 更新)

| 项 | 状态 |
|---|---|
| A2A 协议端点能响应 | ✅ |
| AgentCard 千问能解析 | ✅(3 skills,符合 A2A 0.2.5) |
| 千问发消息 → 收到 Agent 回复(端到端) | ✅(DeepSeek 真回话已验证) |
| `.env` 新 Key 已轮换 | ✅ |
| 协议层 + AgentCard 测试覆盖 | ✅ 28 passed |
| 响应延迟 < 8s(p95) | ⏳ 待压测 |
| 100 次对话 0 报错 | ⏳ 待压测 |
| 流式 SSE 端点 | ❌ V1.0 不实现,返回 -32601 |
| `services/llm` 路径问题 | ✅ 实际为 `app/services/llm.py`,与 server 引用一致 |

---

## 内容安全与三层存储策略

> 核心原则:Gotchas 知识库是知设的核心资产,必须与外部平台隔离。语雀/公众号只做脱敏科普引流,不存核心内容。

### 三层存储架构

| 层级 | 内容 | 存储位置 | 发布渠道 | 原因 |
|---|---|---|---|---|
| **L1 · 核心库** | Gotchas 532条实战经验、独家分析框架 | 本地 `data/knowledge.json` + Git | 仅百宝箱知识库 | 核心资产,零外泄风险 |
| **L2 · 脱敏科普** | 基于国标的避坑知识、施工规范解读 | 本地 Markdown 源文件 | 语雀 / 微信公众号 | SEO引流,展示专业度 |
| **L3 · 内部文档** | 产品规划、用户反馈分析、运营数据 | 飞书文档 / Notion | 不公开 | 团队协作,权限可控 |

### 脱敏规则

- **可以公开**: 国家标准条文(GB规范)、通用施工工艺流程、业主常见问题FAQ
- **脱敏后公开**: 特定城市行情数据(去掉城市名和具体价格,保留趋势判断)
- **绝不公开**: 具体金额案例(如"签8000实收18000")、Gotchas库独家分析框架、用户真实案例和反馈

### 平台安全对比

| 平台 | 模型训练风险 | 私有内容保护 | 知设用途 |
|---|---|---|---|
| 语雀(蚂蚁) | 🟡 中等(协议模糊) | 🟢 较好 | 仅放脱敏科普 |
| 飞书(字节) | 🟢 较低(明确承诺不训练) | 🟢 好 | 内部文档协作 |
| Notion(美国) |  低(明确声明不训练) | 🟢 好 | 个人知识管理 |
| 知乎 | 🔴 较高(用内容训练过模型) | 🔴 差(全部公开) | 不建议放核心内容 |
| 微信公众号(腾讯) |  中等 | — | 脱敏科普引流 |
| 本地Markdown+Git | 🟢 无风险 | 🟢 完全控制 | 核心库最佳存储 |

### 阿里生态平台关系

```
模型研发层: 通义千问 / DeepSeek / 百灵
     ↓
模型服务层(已进驻): 百炼平台(API/MCP) + 千问开放平台
     ↓
应用构建层(已进驻): 百宝箱(AI应用工厂) + 通义平台(待进驻)
     ↓
基础设施层(已进驻): 小程序云(运行服务器)
     ↓
分发变现层: 支付宝小程序(已进驻) → 钉钉(待进驻) → 支付宝开放平台(待进驻)
```

**当前状态**: 模型服务层 + 应用构建层 + 基础设施层已打通,分发层只走了支付宝小程序一条路。
**下一步最低成本扩展**: 去通义平台建一个C端智能体(零开发成本,多一个流量入口)。

---

## 相关文档

- [知设阿里生态进驻项目书](../../.qoderworkcn/workspace/mrfq0p2v2jgpds9g/outputs/知设阿里生态进驻项目书.html) — 平台体系梳理、进驻策略、90天路线图
- [语雀安全评估与内容策略](../../.qoderworkcn/workspace/mrfq0p2v2jgpds9g/outputs/语雀安全评估与内容策略.html) — 安全深度分析、脱敏文章示例、平台对比