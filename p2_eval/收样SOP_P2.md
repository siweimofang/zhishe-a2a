# P2 Step3 收样与评测 SOP

## 一、样张要求

- 数量：10~20 张（报价单 6~12 张 + 装修合同 4~8 张），覆盖不同公司样式（表格式/清单式/拍照/截图）。
- 清晰可读：MVP 只承诺清晰截图；模糊/手写样张欢迎提供，但评测分层计分。
- 合同样张优先拍含关键条款的页面：总价、付款方式、定金、增项、保修、违约、争议解决。

## 二、脱敏规则（红档铁律，上传前必须完成）

1. **涂掉/遮盖**：客户姓名、手机号、微信号、身份证号、详细楼盘门牌、公司抬头（可留"某装饰"）。
2. 工具内置 PII 打码（手机号/身份证）是**兜底护栏不是免责**——当前引擎走 DS 通道（无"不训练"承诺），上传前自行脱敏是硬要求；"未脱净只走百炼或拒收"的硬路由待 spec 落地。
3. 检测方式：若工具报告出现「红档警告」，说明该图未脱净——立即停用该图，重新处理后上传。

## 三、命名与目录

样张丢进 `p2_eval/eval_inbox/`，文件名必须带前缀：

- `contract_xxx.png` = 合同类（走 hetong_shenhe）
- `quote_xxx.jpg` = 报价单类（走 baojia_image_audit）

无前缀的文件会被跳过并提示。

## 四、评测流程（四段式，同 P30）

```bash
cd p2_eval
python prefill_p2.py                 # 1. 扫描 inbox → 实跑插件 → 生成确认包 + 双真值 CSV 骨架
# 2. 人工: 打开 results/confirm_eval_<ts>.md 核对, 在 contract_confirm_<ts>.csv /
#    quote_confirm_<ts>.csv 里只填 truth_* 列(其余列勿动)
python ingest_p2.py --ts <ts>        # 3. 校验+入库(有错整体中止, 防半截数据)
python score_p2.py --prefill results/prefill_<ts>.json   # 4. 四指标评分报告
```

可选：`python prefill_p2.py --repeat 3` 同图跑 3 次，观察提取一致性（0904 演练曾发现 ‰ 换算波动，已修，靠此参数持续盯）。

## 五、真值表填法

**contract_confirm CSV（合同侧）**：每张合同一行。truth_* 列填合同**真实值**：

| 列 | 填法 |
|---|---|
| truth_total / truth_deposit_pct / truth_warranty / truth_waterproof / truth_addition_cap / truth_duration | 数字；合同没写的留空 |
| truth_material_lock | brand_model / brand / equivalent / none / 留空 |
| truth_dispute | arbitration / litigation / 留空 |
| truth_risk_rules | 你人工判断该合同**真实存在**的风险规则名，分号分隔；没有填"无" |

可用规则名（19 条）：`pii_redline, down_payment, tail_payment, payment_sum, payment_sum_low, payment_missing, addition, addition_open, addition_ratio, duration, warranty, warranty_waterproof, breach, delay_penalty, deposit_cap, format_bad, material_lock, warranty_start, payment_progress, penalty_ratio, dispute_missing`

**quote_confirm CSV（报价单侧）**：每个条目一行（AI 预填了提取结果）。

| 列 | 填法 |
|---|---|
| truth_entry / truth_price | 该条目在原图中的真实名称与单价；AI 提取多余的行留空=真值不存在 |
| truth_qty / truth_total | 数量/合价（选填） |
| is_pit | 1=该条目是埋的坑（虚高/漏算/欺诈），0=正常条目 |
| pit_type | overprice（单价虚高）/ missing（该有而没有）/ fraud（套路） |

## 六、指标口径

- 报价单：条目召回率（真值条目被提取的比例）、单价提取准确率（±1%）、坑命中率（埋坑被报出的比例）、误报率（报出的坑中不是坑的比例）。
- 合同：字段提取准确率（数字 ±5%、枚举精确）、规则命中率（truth_risk_rules ∩ AI 命中）、规则误报率（AI 命中 − truth）。
- FP 处理原则：逐案核对区分「提取误差」vs「规则阈值问题」，聚类分析优先于改阈值——防止过拟合小样张。
