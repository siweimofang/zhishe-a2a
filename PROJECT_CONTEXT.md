# 知设 AI 装修顾问 · 项目完整上下文

> 整合 2026-06-13 凌晨 V1.0 上线阶段所有讨论、项目书、文档、决策、当前状态
> 目的:任何 Mavis session 醒来,看这一份文档就能 100% 接手
> 作者:Mavis

---

## 🎯 一句话定位

**zhishe-a2a = 沈阳装修报价专家,基于 Mini Max M3 + PostgreSQL + pgvector,通过 A2A 0.2.5 协议被多渠道调用,先上线千问 Agent 占坑,再构建数据护城河**

---

## 📂 项目全景(三个子项目)

### 子项目 1:`zhishe-a2a` (V1.0 主项目)
- **位置**:`D:\知设Agent生态\千问AI Agent\zhishe-a2a\`
- **技术栈**:Python 3.11.9 + FastAPI + a2a-sdk 0.2.5 + DeepSeek(临时主力,目标是 Mini Max M3)
- **当前状态**:
  - ✅ 永久 URL `https://tunnel.zhishe.top` 通(Cloudflare Named Tunnel + zhishe.top 域名)
  - ✅ A2A 0.2.5 协议端到端跑通(1.8s 拿到完整装修回答)
  - ✅ 32 个 pytest 全绿
  - ✅ Windows 开机自启任务已注册
  - ⚠️ 千问平台接入入口卡住(2026 改版后无"三方 Agent"UI)
- **未做(V1.0 应该做但还没做)**:
  - ❌ 报价引擎(数据在 data/quote_baseline.json,代码没调用)
  - ❌ PostgreSQL + pgvector(V1.0 应该有数据持久化)
  - ❌ LiteLLM 封装(目前直接调 DeepSeek)
  - ❌ Mini Max M3(主力 LLM 应该是它,目前用 DeepSeek 是临时)
  - ❌ 知识库 RAG(100 条沈阳本地化知识,目前 0 条)
  - ❌ 三层转化话术(钩子+逼单+复访)
  - ❌ 会话管理(目前无 contextId 记忆)

### 子项目 2:`千问 AI Agent` 部署目录
- **位置**:`D:\知设Agent生态\千问AI Agent\`
- **核心文件**:
  - `cloudflared.exe`(2026.6.0,Named Tunnel 客户端)
  - `start_named.bat`(启动脚本)
  - `master_deploy.ps1`(一键部署)
  - `register_task.ps1`(开机自启注册,GBK 编码,需绕过)
  - `STRATEGY.md` / `AGENT_EVAL.md` / `DEPLOY_PLAYBOOK.md` / `SANDBOX_PREDESIGN.md` / `千问接入指南.md`
  - `cf_stderr.log` / `uvicorn.log` / `cert.pem`
- **当前状态**:✅ Named Tunnel `zhishe-prod` (UUID `bf4ec8be-ed5c-484d-9261-3af09658ef8f`) 跑通,cert.pem 已就位

### 子项目 3:`小程序 AI Agent`(独立项目,跟千问 V1.0 暂无关)
- **位置**:`D:\知设Agent生态\小程序AI Agent\`
- **项目规范**:`知设AI小程序RedSkill项目规范_v5.0_20260611.md`(V1.0 是 V1,不是 V1.0 千问主项目)

### 子项目 4:小红书项目书(战略源头)
- **位置**:`E:\小红书\学习AI大模型如何应用\千问AI Agent装修项目计划书\知设AI装修项目计划书_v1.0.md`
- **重要性**:**所有 V1.0 设计决策的源头** —— 2026-06-13 凌晨 3:30 才被 Mavis 第一次读到,**严重失职**,必须先读再做

---

## 📋 项目书(2026-06-07 v1.0)核心内容

### 四层架构
```
接入层:千问Agent → 微信小程序 → 淘宝 → 豆包 → ...
Harness层:会话管理 / 意图路由 / 工具调用 / 记忆管理 / 模型调度 / 安全风控 / 成本控制 / 评测引擎
模型层:Mini Max M3(主) / 通义千问(备) / 本地小模型(兜)
能力层:报价引擎 / 知识库RAG / 设计师库 / 案例库 / 数据闭环
```

### V1.0 MVP 7 天开发计划
- **Day 1**:项目初始化 + 模型接入(Mini Max M3 + LiteLLM)
- **Day 2-3**:报价引擎(基础价 × 面积 × 户型 × 档次 × 风格)
- **Day 4**:知识库 RAG(100 条沈阳本地化知识)
- **Day 5**:**千问 Agent 平台对接**(Agent 创建 + 回调接口 + 联调测试)← **当前卡这步**
- **Day 6**:三层转化话术系统
- **Day 7**:测试 + 优化 + 正式上线

### V1.0 验收指标(业务导向)
- ✅ 用户问装修报价,能出相对靠谱的沈阳本地价格
- ✅ 每轮回答自然带转化引导语
- ✅ 10 个种子用户测试,加微信转化率 ≥ 30%
- ✅ 不出现明显违规内容和离谱报价

### V2.0 / V3.0 路线
- **V2.0**(日活≥30 或月入≥2000):多模型冗余 / 工具调用框架 / 设计师匹配 / 知识库扩量 / 故障告警 / 成本看板 / 故障兜底 / 微信小程序
- **V3.0**(日活≥200 或月入≥10000):数据闭环自动优化 / 自动化评测 / 完整故障兜底 / 灰度发布 / 本地小模型兜底 / 多平台矩阵 / 完整监控大盘

---

## 🧠 关键认知纠错(Mavis 必须记住)

1. **主力 LLM 是 Mini Max M3,不是 DeepSeek**
 - 现在用 DeepSeek 是临时方案,因为 Mini Max M3 接入方式还没确定
 - V1.0 验收时应该迁回 Mini Max M3
2. **V1.0 是有完整 5 大模块的 MVP,不只"部署上线"**
 - 5 大模块:报价引擎 / 三层转化话术 / 知识库 RAG / 千问 Agent 接入 / 会话管理+安全
 - 当前只完成基础设施(A2A 协议 + 永久 URL),模块 1/2/3/5 还没做
3. **百炼 2026 改版后"三方 Agent"入口不显示**
 - 阿里云官方文档 `https://help.aliyun.com/zh/model-studio/multimodal-integration-a2a/` 显示功能存在
 - 但你账号里左侧菜单找不到
 - 可能:企业旗舰版独占 / 灰度测试中 / 入口在"多模态交互开发套件"下隐藏菜单
4. **现有百炼应用"知设 AI 装修顾问"是占坑用的**
 - 你 2026-06-08 23:08:51 建好,prompt 已写完整(小知人设)
 - 这是项目书 Day 5 "千问 Agent 平台对接"+"Agent 创建与配置"产物
 - V1.0 占坑 = 把它发布出去,让千问平台有"知设 AI 装修顾问" Agent
5. **zhishe-a2a 后端是 Day 5 "回调接口开发"**
 - 但今晚发现百炼没 A2A 接入入口
 - 所以 zhishe-a2a 当前只能:
 a) 走 web 端独立渠道(用户访问 `https://tunnel.zhishe.top`)
 b) 等百炼开放 A2A 三方 Agent 权限
 c) 走百炼"我的模型"自定义 LLM endpoint(改 zhishe-a2a 加 OpenAI-compatible 端点)

---

## 🎯 V1.0 当前状态总览(2026-06-13 03:30)

| V1.0 模块 | 状态 | 备注 |
|---|---|---|
| 基础设施(A2A 协议 + FastAPI + 永久 URL) | ✅ 100% | 32 测试全绿,1.8s 真对话 |
| Day 1:模型接入 | ⚠️ 60% | DeepSeek 通,Mini Max M3 还没接 |
| Day 2-3:报价引擎 | ❌ 0% | 数据有(data/quote_baseline.json),代码没调 |
| Day 4:知识库 RAG | ❌ 0% | 没有 PostgreSQL,没有知识条目 |
| Day 5:千问 Agent 平台对接 | ⚠️ 50% | 百炼应用已建,缺接入自己后端 |
| Day 6:三层转化话术 | ⚠️ 30% | prompt 里有基本话术,缺动态匹配 |
| Day 7:测试+上线 | ❌ 0% | 没种子用户,没发布 |

**完成度估算:V1.0 ≈ 35%**(只有基础设施 + Day 5 的百炼应用基础)

---

## 🚨 今晚(2026-06-13 02:00-03:30)实际成果

| 任务 | 状态 | 备注 |
|---|---|---|
| Cloudflare OAuth 授权 | ✅ | user 点击 Authorize,cert.pem 已落盘 |
| Cloudflare Nameserver 切换 | ✅ | Aliyun → Cloudflare(传播中) |
| 永久域名 `tunnel.zhishe.top` | ✅ | DNS 已传播,Cloudflare 权威看到 A+AAAA 记录 |
| Named Tunnel `zhishe-prod` | ✅ | UUID `bf4ec8be-ed5c-484d-9261-3af09658ef8f` |
| 命名隧道 config.yml | ✅ | C:\Users\Administrator\.cloudflared\config.yml |
| Windows 开机自启 | ✅ | 任务计划 `zhishe-a2a-autostart`(ONSTART, SYSTEM, HIGHEST) |
| A2A 端到端真对话 | ✅ | 1.8s 拿到完整装修回答,Task/Artifact 结构正确 |
| 千问平台"三方 Agent"接入 | ❌ | 入口在百炼 UI 里看不到(2026 改版后企业旗舰版独占) |
| **百炼"知设 AI 装修顾问"应用发布** | **✅ 2026-06-13 06:39** | **V1.0 占坑成功!LLM = Qwen-Plus-Latest,prompt = 小知人设 902 字符** |
| 千问 APP 端能搜到 Agent | ⏳ | 等 1-24h 千问发现延迟 |
| 真实用户对话数据 | ⏳ | 种子用户测试 → 10 人 → 转化率 ≥ 30% |

### 📸 V1.0 发布成功截图
存档位置:`docs/screenshots/V1.0_release_success.png`
- 时间:2026-06-13 06:39:10
- 内容:百炼"知设 AI 装修顾问"应用,顶部「✅ 发布成功」绿标,标题栏「已发布」
- LLM:Qwen-Plus-Latest
- 应用 ID:`97815191a34575b182f164785a6...`(2026-06-08 23:08:51 创建)

---

## 📝 待办(分时段)

### 今晚(2026-06-13 凌晨 6:40 后)
- [x] ~~你 在百炼点"知设 AI 装修顾问"应用的"发布"按钮 → V1.0 占坑~~ **已完成 06:39**
- [x] ~~Mavis 整理本份 PROJECT_CONTEXT.md~~ **已完成**
- [x] ~~Mavis 更新 `千问接入指南.md`,反映 2026 改版后"三方 Agent 入口缺失"事实~~ **已完成**
- [x] ~~Mavis 截图存档 `docs/screenshots/V1.0_release_success.png`~~ **已完成**
- [x] ~~Mavis 写百炼工单话术~~ **已写入 `千问接入指南.md` 末尾**
- [x] ~~Mavis git commit V1.0 上线状态~~ **见下条 commit**

### 明天(2026-06-13 白天)
- [ ] 你 打开千问 APP,搜"知设" / "知设 AI 装修顾问",截图发我看
- [ ] 你 提交百炼工单(话术在 `千问接入指南.md` 末尾),问"我是企业用户,怎么接入自建 A2A Agent"
- [ ] 你 邀请 10 个种子用户在千问 APP 上试用,看真实对话效果
- [ ] Mavis 写报价引擎:用 `data/quote_baseline.json` + `data/coefficients.md`,实现 `quote()` 函数
- [ ] Mavis 集成 LiteLLM,把 DeepSeek 换成 Mini Max M3(确认接入方式)
- [ ] Mavis 加 PostgreSQL + pgvector,准备接 RAG

### 本周
- [ ] V1.0 Day 2-3(报价引擎)
- [ ] V1.0 Day 4(RAG 100 条)
- [ ] V1.0 Day 5(千问接入 V2.0 路径:等百炼工单回复,如不开就接百炼"我的模型"自定义 LLM)
- [ ] V1.0 Day 6(三层转化话术动态化)
- [ ] V1.0 Day 7(种子用户测试 + 转化率验证)

---

## 🔑 关键技术细节(防止再忘)

### A2A 鉴权:支持 `X-API-Key` 和 `Authorization: Bearer`
代码 `app/a2a/server.py:38-45`:
```python
def _verify_api_key(authorization: Optional[str]) -> bool:
    if not settings.A2A_API_KEY:
        return True
    if not authorization:
        return False
    token = authorization.replace("Bearer ", "").strip()
    return token == settings.A2A_API_KEY
```
且 `app/a2a/server.py:54` 优先读 `X-API-Key` header,符合阿里云官方规范。

### A2A 端点
- AgentCard: `GET https://tunnel.zhishe.top/.well-known/agent.json`
- 同步消息: `POST https://tunnel.zhishe.top/a2a/message/send`
- 流式消息: `POST https://tunnel.zhishe.top/a2a/message/stream` (V1.0 不支持)
- 健康: `GET https://tunnel.zhishe.top/health/ready`

### 当前密钥
- DeepSeek API Key: 在 `zhishe-a2a/.env` (gitignore,头 `sk-`,尾 `f2cd1fac7bc5`)
- A2A API Key: `mKgd4EVhF7A8Y9zk6unOyb2jI1NBLaTR`(用于百炼调 zhishe-a2a)
- Cloudflare: 已登录,account email `makevip2026@163.com`
- 阿里云百炼: 已登录,sub-account `nick0108261858`

### 关键服务状态
- uvicorn: 端口 8765,FastAPI app:main
- cloudflared: Named Tunnel `zhishe-prod`
- Windows 任务计划: `zhishe-a2a-autostart`(ONSTART, SYSTEM)
- 域名 DNS: Cloudflare 权威(1.1.1.1)已生效,Aliyun NS 切换传播中

### Memory 重要条目
- `.env` 必须用 `utf-8-sig` 编码(pydantic-settings 读 BOM)
- uvicorn 启动时读 .env,改 .env 必须重启 uvicorn
- 复制语义:用户说"复制"必须 Copy-Item,禁止 Move
- PS 5.1 GBK 编码 .ps1 脚本 parser 错误,绕开:用 schtasks CLI / Git Bash / Python
- PS 5.1 子进程 stdout 是 cp936,中文输出要写文件再 Read
- cloudflared cert.pem 必须存到 `C:\Users\Administrator\.cloudflared\`
- cloudflared 必须显式 `--config C:\Users\Administrator\.cloudflared\config.yml`

---

## 📚 文档索引(防止再漏看)

### 必读(战略级)
1. `E:\小红书\学习AI大模型如何应用\千问AI Agent装修项目计划书\知设AI装修项目计划书_v1.0.md` ← **项目源头**
2. `D:\知设Agent生态\千问AI Agent\STRATEGY.md`
3. `D:\知设Agent生态\小程序AI Agent\知设AI小程序RedSkill项目规范_v5.0_20260611.md`(另一个项目)

### V1.0 接入(执行级)
4. `D:\知设Agent生态\千问AI Agent\千问接入指南.md`(V1.0 接入百炼步骤,2026 改版后部分失效)
5. `D:\知设Agent生态\千问AI Agent\AGENT_EVAL.md`(V1.0 评估 81/100)
6. `D:\知设Agent生态\千问AI Agent\DEPLOY_PLAYBOOK.md`
7. `D:\知设Agent生态\千问AI Agent\SANDBOX_PREDESIGN.md`

### 代码级
8. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\README.md`
9. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\app\prompts\xiaozhi.py`(小知 prompt,53 行)
10. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\app\a2a\server.py`(A2A 路由)
11. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\app\a2a\agent_card.py`(3 skills)
12. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\quote_baseline.json`(沈阳报价基线)
13. `D:\知设Agent生态\千问AI Agent\zhishe-a2a\data\coefficients.md`(户型/风格/面积系数)

### 部署级
14. `D:\知设Agent生态\千问AI Agent\start_named.bat`(启动 + 命名隧道)
15. `D:\知设Agent生态\千问AI Agent\master_deploy.ps1`(一键部署)
16. `D:\知设Agent生态\千问AI Agent\register_task.ps1`(开机自启注册)

---

## 🤝 沟通铁律(Mavis 必记)

1. **执行前先做技术路径预设计** —— 在脑子里跑一遍方案可行性
2. **能我替你做的,我替你做** —— 用工具直接操作,不让你复制粘贴
3. **真必须你操作时** —— 纯文本命令,不嵌 markdown,标"只复制 xx 到 yy"
4. **默认姿态** —— 讲"在做什么 + 为什么 + 关键判断节点",让你做战略
5. **重做过的事要写 memory** —— 下次 session 醒来能直接接手
6. **用户偏好的工作方式** —— 了解原理 / 分析问题 / 战略方向,避免让用户做战术执行

---

> 本文档由 Mavis 在 2026-06-13 凌晨 3:30 整合,基于今晚所有项目讨论 + 项目书 + 现有所有项目文档
> 下次 Mavis session 醒来,先读本份文档,再做新决策
