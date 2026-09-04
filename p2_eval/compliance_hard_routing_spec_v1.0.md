# 合规硬路由 Spec v1.0（定稿草稿）

> 批次四交付物①。状态：**草稿待拍板**（3 个待拍板项见 §7）。拍板后实现工作量约 0.5 天（估）。
> 依据（代码事实）：
> - `contract_ocr.js:8-11` 红线注释：合同原件属红档永不上云；v0.5.0 检出 PII 且供应商非百炼时附 `compliance_warning`（提示级），「未脱净只走百炼或拒收」硬路由留待本 spec。
> - `providers.js` v0.5.0：双路线注册表 `deepseek`（默认）/ `bailian`（BAILIAN_API_KEY + BAILIAN_VL_MODEL 注入型号，**当前环境未配置**）。
> - `contract_engine.js:149-153`：PII 红档旗标已是 SEV_CRITICAL 最高优先（`pii_redline`）。
> - `maskPII`（contract_ocr.js:51-61）：手机号/身份证号正则打码，检出清单随返回值 `pii.found`。
> - 后端 `cost_router.py:276-287`：文本侧已有 compliance 优先路由（→qwen3.8-max/百炼，fallback qwen3.5-plus）。本 spec 只管**视觉侧**（插件）。

---

## 1. 目标与范围

红档 = 合同原件及一切含个人身份信息（PII：手机号/身份证号）的装修文档。红线（项目书 §5）：**红档原件永不上非合规云**（DeepSeek 等无"不训练"承诺的通道）。

本 spec 定义三件事：什么件算红档（档级判定）、红档走什么路（路由规则）、不满足时拒不拒（降级路径）。范围仅插件视觉链路；文本路径不经视觉云，天然不触线（文本进 LLM 按后端 cost_router 既有 compliance 规则走）。

## 2. 档级与通道

**档级（按工具输入类型判定，非按内容判定——内容在提取前不可知，这是预检的设计约束）：**

| 工具 | 输入 | 档级 |
|---|---|---|
| `hetong_shenhe`（图片路径） | 合同条款页截图 | **红档**（工具描述已强制"必须脱敏件"） |
| `baojia_image_audit` / `baojia_shenhe` | 报价单 | 蓝档（业界无红档定性；PII 后检仍生效） |
| `baojia_item_check` | 单项名称 | 无图像，不触线 |
| 全部工具的文本路径 | 用户粘贴文本 | 不经视觉云，不触视觉红线 |

**通道：** 合规通道 = `bailian`（百炼，数据在阿里云）；普通通道 = `deepseek`（默认）。`VISION_PROVIDER` 环境变量只决定默认通道，**不覆盖本 spec 的工具级强制**。

## 3. 触发矩阵（核心）

**预检（调用前，按上表档级 × COMPLIANCE_MODE）：**

| 场景 | mode=strict | mode=advisory（现状默认） |
|---|---|---|
| hetong_shenhe 图片 + 供应商=bailian | 放行 | 放行 |
| hetong_shenhe 图片 + 供应商≠bailian | **拒收**（不发起任何视觉调用），错误文案给两条出路：①配置 BAILIAN_API_KEY+BAILIAN_VL_MODEL 走百炼；②改传彻底脱敏件或粘贴条款文本（文本路径） | 放行，PII 后检兜底（= v0.5.0 现状） |
| baojia_image_audit 图片 | 不限供应商 | 不限供应商 |

**后检（提取文本 PII 扫描，maskPII 已有，不可省——预检挡不住"用户拿报价单工具传合同"的绕行）：**

| 场景 | strict | advisory |
|---|---|---|
| 检出 PII + 供应商=bailian | 通过（合规通道），打码照旧，`pii.found` 照常返回 | 同左 |
| 检出 PII + 供应商≠bailian | 调用已发生不可撤回 → 结果标记 `compliance_blocked: true`，报告顶部红档警告 + **结果封存口径**（§7-③）：该样张结论仅限本机核对，禁止进入对外交付物；并在日志记录事件 | `compliance_warning` 提示文案（v0.5.0 现状，一字不改） |
| 未检出 PII | 正常 | 正常 |

关键设计说明（为什么预检按工具类型不按内容）：PII 扫描发生在 OCR **之后**（contract_ocr.js:118 先提取后打码），"检出 PII 再改走百炼重发"意味着敏感图已经发过一次 DeepSeek——违规已成事实。所以硬路由必须是**事前门**（合同工具=红档，默认走百炼），PII 后检只能做"事后封存+警示"，两者缺一不可。

## 4. 降级路径（不装死原则，对应框架自查第十节④：框架外活动不得泄漏）

1. **bailian 未配置**（BAILIAN_VL_MODEL 或 BAILIAN_API_KEY 缺失）：strict 下 hetong_shenhe 图片路径拒收，文案给两选一（配百炼 / 改脱敏件或文本路径）。**不做静默降级到 DeepSeek**——静默降级=用户不知情的模式转换。
2. **百炼调用失败**（网络/限额/限流）：strict 下重试 1 次 → 仍失败 → 明确报错拒收，不回落 DeepSeek。advisory 下维持现状（直接报错）。
3. **文本路径永远可用**：粘贴条款文本不经视觉云，是天然合规兜底，拒收文案必须引导到这条路。

## 5. 配置与环境变量

| 变量 | 取值 | 说明 |
|---|---|---|
| `COMPLIANCE_MODE` | `advisory`（默认）/ `strict` | 默认值=现状行为，切换 strict 需满足 §6 切换条件 |
| `BAILIAN_API_KEY` | 已有后端配置可复用 | strict 前置条件 |
| `BAILIAN_VL_MODEL` | 百炼控制台当前主力 VL 型号 | **当前未配置**——strict 前置条件 |
| `VISION_PROVIDER` | deepseek / bailian | 仅默认通道，不覆盖工具级强制 |

## 6. 实现落点（拍板后 0.5 天估）

1. `contract_ocr.js` `extractContractFromImages` 入口加预检门：strict + 解析供应商≠bailian → 直接 return `{success:false, compliance_refused:true, error:文案}`（复用 `resolveVisionProvider` 解析结果，不新增请求）。
2. `contract_ocr.js` 后检分支按 mode 分流：strict 时输出 `compliance_blocked` 标记（advisory 保持 `compliance_warning` 原样，**零行为变化**）。
3. `index.js` `hetong_shenhe` 工具层透出拒收错误；工具描述补一句"strict 模式下未脱敏件将被拒收"。
4. 测试：`test/` 新增 3 断言（strict+deepseek→拒收不发起调用；strict+bailian→放行；advisory+deepseek+PII→warning 文案与 v0.5.0 逐字一致）。
5. **切换条件**（advisory→strict）：①BAILIAN_VL_MODEL 配置就位；②百炼路线实测 1 张脱敏合同样张提取成功；③用户拍板。

## 7. 待拍板项（3 个）

1. **strict 切换时机**：建议=百炼 VL 验证通过后即切；代价=未配百炼的新环境合同图片功能不可用（文案会引导文本路径）。
2. **报价单是否升级为红档**：建议=暂不（报价单 PII 密度低且已有后检提示；升级会牺牲报价图片在 DeepSeek 路线的可用性）。若升级，`baojia_image_audit` 同样受预检门约束。
3. **strict 下"结果封存"口径**：检出 PII 且走错通道时，结果标记 compliance_blocked 后——A 仅日志警示（建议，改动最小）；B 报告内嵌红色横幅；C 直接丢弃本次结果要求重跑。涉对外交付时的口径需明确。
