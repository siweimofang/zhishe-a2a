# -*- coding: utf-8 -*-
"""Layer-2 独立验证器：批量验证 standard 条目（验证者与生成者隔离）。

设计要点（对应 Graph Engineering 文章"验证必须独立于创造"）：
  1. 上下文隔离：验证 prompt 只含 条目全文 + 相关真理表规则 + 废止条文须知，
     不含任何生成过程/推理链/中间结论
  2. 反推式验证：系统角色明确要求"尝试推翻条目，而不是确认它"
  3. 结构化输出：{"decision": pass|fail|retry, "issues": [{field, problem, evidence}]}
     —— 返回证据，而不是感觉
  4. 模型可切换：默认 DEEPSEEK_*；配置 SECOND_MODEL_BASE_URL/API_KEY/MODEL 后
     自动切换为第二家模型（真独立验证）

用法: python gotchas/pipeline/layer2_verify.py [--limit N] [--ids GZ-SY-00564,GZ-SY-00565]
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a"
DATA = ROOT + r"\gotchas\data\v1.0\all_ku.json"
RULES = ROOT + r"\gotchas\data\v1.0\verification_rules.json"
ENV = ROOT + r"\.env"
REPORT = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\outputs\layer2_verify_report_20260804.md"

ABOLISHED_NOTE = ("效力状态须知：\n"
                  "1. GB 50210-2018 原强制性条文 3.1.4/6.1.11/6.1.12/7.1.12/11.1.12 已于 2023-03-01 废止，"
                  "其要求在 GB 55032-2022（全文强制）中承接执行。\n"
                  "2. GB 50327-2001《住宅装饰装修工程施工规范》现行有效、并未废止，但其中 8 条原强制性条文"
                  "（3.1.3/3.1.7/3.2.2/4.1.1/4.3.4/4.3.6/4.3.7/10.1.6，建标[2001]266号公告确认）"
                  "自 2025-05-01 起废止（住建部2025年第39号公告发布 GB 55038-2025《住宅项目规范》承接执行）。"
                  "条文内容作为一般性规定仍有效，但条目不得再称其为'强制性条文'，且应注明承接关系。\n"
                  "3. 条目若引用已废止条文且未注明废止/承接关系，视为效力状态错误。")

STANDARD_BG = """标准背景知识（已人工核实的权威事实，作为判定基准，与条目内容不一致时以本段为准）：

【JGJ/T 304-2013《住宅室内装饰装修工程质量验收规范》】章节目录：3基本规定、4基层工程、5防水工程、6门窗工程、7吊顶工程、8轻质隔墙工程、9墙饰面工程、10楼地面饰面工程、11涂饰工程、12细部工程、13厨房工程、14卫浴工程、15电气工程、16智能化工程、17给水排水与采暖工程、18通风与空调工程、19室内环境污染控制、20工程质量验收程序。
- 3.0.2 材料进场验收（品种/规格/包装/外观/尺寸+验收记录+质量证明文件+复验+见证取样）；3.0.4 严禁拆承重墙/损坏受力钢筋；3.0.5 施工前交接检验记录；3.0.8 一般项目合格率≥80%且最大偏差≤1.5倍允许偏差。
- 4.2.1/4.3.2 基层空鼓：单处面积≤0.04m²、每间≤2处。
- 9.2.2 满粘法饰面砖应无空鼓（墙面砖本身不允许空鼓）。
- 15.3.5 导线色标：黄绿双色=保护线、淡蓝色=中性线；15.6.1 卫生间局部等电位联结（强制）；15.6.2 联结导线≥4mm²。
- 17.2.1 水压试验符合设计要求并通水试验（数值在条文说明：试验压力为工作压力1.5倍且≥0.6MPa）；17.2.7 左热右冷、间距与设备接口匹配。
- 20.0.3 分户验收（附录D/E/F）。第5章防水工程正文无蓄水数值，蓄水24h/水位下降≤20mm/淋水高度1.8m出自 JGJ 298-2013。
- 注意：本规范无"三阶段验收"等字面表述（属行业归纳）；无冷热水管150mm间距、无管卡间距数值条文（属行业习惯）。

【GB 50327-2001《住宅装饰装修工程施工规范》】现行有效（未被2013版替代，也不存在2017/2019版替代之说）。
- 3.1.3 严禁损坏绝热设施和受力钢筋、严禁超载堆放、严禁在预制空心楼板上打孔（原强条，2025-05-01废止强条地位）；3.1.7 临时用电（开关箱应装漏电保护器）；3.2.2 严禁使用国家明令淘汰的材料（原强条）；3.2.4 进场验收（不含"进口产品应进行商品检验"——该句在 GB 50210-2018 3.2.4）；4.1.1 防火制度；4.3.4 明火作业清除可燃物+专人监护；4.3.6 严禁吸烟；4.3.7 严禁焊接运行中的管道、易燃易爆容器及受力构件。

【GB 50210-2018《建筑装饰装修工程质量验收标准》】8.1.3 人造木板甲醛释放量复验（石膏板不是人造木板）；10.2.4 内墙满粘法饰面砖无裂缝、大面阳角无空鼓；10.3.5 外墙饰面砖无空鼓裂缝；表10.2.8 内墙饰面砖允许偏差：立面垂直度2mm、表面平整度3mm、阴阳角方正3mm、接缝直线度1mm、接缝高低差0.5mm（钢直尺+塞尺检查）、接缝宽度1mm；6.4.5 滑撑螺钉材质不锈钢（主控）；6.6.1 玻璃层数/品种/规格/尺寸/色彩/图案/涂膜朝向符合设计要求（镀膜玻璃膜面朝内在条文说明6.6.1）。GB 50209-2010 6.2.7 原文：面层与下一层结合(粘结)应牢固、无空鼓（单块砖边角允许有局部空鼓，但每自然间或标准间的空鼓砖不应超过总数的5%），检验方法为小锤轻击——5% 是该条正文数值，不是条文说明。

【GB 50242-2002《建筑给水排水及采暖工程施工质量验收规范》】4.2.1 水压试验分档：金属管10min压降≤0.02MPa；塑料管1h压降≤0.05MPa且2h压降≤0.03MPa。0.6~0.8MPa试验压力是行业口径（条文说明级），不是该条正文数值。

【无依据数据清单（条目若含以下数值不得判错，但应提示为行业习惯而非条文）】：
- 饰面砖"单块空鼓面积≤10%"：无任何国标依据（已废弃说法）
- 等电位联结电阻≤3Ω：行业通行引用值（GB 50303-2015 第25章正文无电阻限值），0.03Ω/0.1Ω 无依据
- 冷热水管间距150mm、管卡间距600~800mm：行业习惯，无国标条文"""

SYSTEM_PROMPT = """你是"知设知识库"的独立质量验证器（Inspector）。

你掌握一份已人工核实的标准背景知识（上方 STANDARD_BG 段），凡与背景知识冲突的"标准常识"记忆一律以后者为准；背景知识中标注"无依据/行业习惯"的数值，不得作为错误判据。""" + STANDARD_BG + """

工作准则：
1. 你的目标是**尝试推翻**给定条目，而不是确认它。一个条目只有当你在标准条文与真理表数值面前找不到任何可攻击点时，才判 pass。
2. 判定依据只有三样：条目本身、标准条文锚点（standard_number）、真理表规则。你没有任何关于条目生成过程的信息，也不应假设"入库时已核对过"。
3. 每个问题必须附证据（具体条文号、数值、矛盾点）。"感觉不对"不构成问题。
4. 问题分两级，type 必须二选一：
   - "error"：事实错误——数值错误、条文号错误、标准混淆（如材料限量与空气浓度混写）、废止条文无承接、指标表述与标准矛盾
   - "improvement"：完善建议——不够详细、未指明版本、可量化而未量化（不构成事实错误）
   只有存在 type=error 时才判 fail；只有 improvement 时判 pass（建议照记）。
5. 输出必须是单个 JSON 对象（不要输出其他文字）：
{
  "decision": "pass" | "fail" | "retry",
  "confidence": 0.0-1.0,
  "issues": [
    {"field": "standard_number/standard_requirement/compliance_criteria/效力状态/其他",
     "type": "error" | "improvement",
     "problem": "问题描述",
     "evidence": "证据（条文号/数值/矛盾点）"}
  ]
}
decision 定义：
- pass：无事实错误（允许 improvement 建议，计入"改进建议"）
- fail：存在 type=error 的事实错误
- retry：证据不足无法判定（如标准锚点过于笼统、规则未覆盖），需人工确认"""


def load_env():
    env = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8-sig"):  # utf-8-sig 去 BOM
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def api_config():
    env = load_env()
    if env.get("SECOND_MODEL_BASE_URL") and env.get("SECOND_MODEL_API_KEY"):
        return {
            "base_url": env["SECOND_MODEL_BASE_URL"].rstrip("/"),
            "key": env["SECOND_MODEL_API_KEY"],
            "model": env.get("SECOND_MODEL", "glm-4-plus"),
            "provider": "second_model",
        }
    return {
        "base_url": env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "key": env["DEEPSEEK_API_KEY"],
        "model": env.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "provider": "deepseek",
    }


def call_llm(cfg, messages, timeout=120):
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(cfg["base_url"] + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + cfg["key"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_json(text):
    text = text.strip()
    # 先剥离 markdown 代码块（```json ... ``` / ``` ... ```）
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if m:
        text = m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def related_rules(k, rules):
    text = (k.get("standard_number", "") + k.get("standard_requirement", "") +
            k.get("compliance_criteria", ""))
    hits = [r for r in rules if r.get("keywords") and any(kw in text for kw in r["keywords"])]
    return hits


def build_user_prompt(k, rules_cfg):
    rules = related_rules(k, rules_cfg["rules"])
    rules_txt = json.dumps(rules, ensure_ascii=False, indent=1) if rules else "（无相关真理表规则命中，请以标准常识与条文号自证）"
    ku_txt = json.dumps({kk: k.get(kk) for kk in
                         ["ku_id", "title", "knowledge_type", "standard_number", "standard_authority",
                          "standard_requirement", "compliance_criteria", "verification_method",
                          "description", "related_ku_ids"]}, ensure_ascii=False, indent=1)
    return f"""待验证条目（完整 JSON）：
{ku_txt}

相关真理表规则（用于核对数值，若字段为空则该规则无数值要求）：
{rules_txt}

{ABOLISHED_NOTE}

请输出验证结果 JSON。"""


def main():
    args = sys.argv[1:]
    limit = None
    only_ids = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--ids" in args:
        only_ids = set(args[args.index("--ids") + 1].split(","))

    kus = json.load(open(DATA, encoding="utf-8"))
    rules_cfg = json.load(open(RULES, encoding="utf-8"))
    std = [k for k in kus if k.get("knowledge_type") == "standard"]
    if only_ids:
        std = [k for k in std if k["ku_id"] in only_ids]
    if limit:
        std = std[:limit]

    cfg = api_config()
    print(f"验证服务={cfg['provider']} 模型={cfg['model']} 目标条目={len(std)}", flush=True)

    results = []
    for i, k in enumerate(std, 1):
        kid = k["ku_id"]
        for attempt in range(2):
            try:
                resp = call_llm(cfg, [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(k, rules_cfg)},
                ])
                raw = resp["choices"][0]["message"]["content"]
                verdict = extract_json(raw) or {}
                if not verdict:
                    # 解析失败：把原始返回写入调试日志，便于人工诊断
                    dbg = r"C:\Users\Administrator\.qoderworkcn\workspace\mrfq0p2v2jgpds9g\layer2_raw_debug.log"
                    with open(dbg, "a", encoding="utf-8") as f:
                        f.write(f"\n===== {kid} 解析失败 {time.strftime('%H:%M:%S')} =====\n{raw}\n")
                results.append({"ku_id": kid, "title": k["title"][:30], "verdict": verdict, "raw": raw[:200]})
                d = verdict.get("decision", "?")
                n_issues = len(verdict.get("issues", []))
                d_cn = {"pass": "通过", "fail": "不通过", "retry": "待复核"}.get(d, "未知")
                print(f"[{i}/{len(std)}] {kid} -> {d_cn} 问题数={n_issues} 置信度={verdict.get('confidence')}", flush=True)
                break
            except Exception as e:
                print(f"[{i}/{len(std)}] {kid} 第{attempt + 1}次调用失败: {e}", flush=True)
                if attempt == 1:
                    results.append({"ku_id": kid, "title": k["title"][:30],
                                    "verdict": {"decision": "retry", "issues": [{"problem": f"接口调用失败: {e}"}]}})
                time.sleep(2)

    # ---------------- 报告 ----------------
    cnt = {}
    for r in results:
        cnt[r["verdict"].get("decision", "?")] = cnt.get(r["verdict"].get("decision", "?"), 0) + 1

    def errs(v):
        return [i for i in v.get("issues", []) if i.get("type") == "error"]

    def imps(v):
        return [i for i in v.get("issues", []) if i.get("type") != "error"]

    lines = []
    lines.append("# Layer-2 独立验证报告（验证者与生成者隔离）")
    lines.append("")
    lines.append(f"> 验证时间：2026-08-04 ｜ 验证服务：{cfg['provider']}（{cfg['model']}）")
    lines.append(f"> 验证原则：上下文隔离（无生成过程）+ 反推式验证（尝试推翻）+ 结构化证据输出")
    lines.append(f"> 验证对象：{len(results)} 条 standard 条目 ｜ 判定口径：仅存在事实错误（error）判不通过，完善建议（improvement）计入改进建议")
    lines.append("")
    lines.append("## 一、总览")
    lines.append("")
    lines.append(f"- 通过：{cnt.get('pass', 0)} 条（含带改进建议的通过）")
    lines.append(f"- 不通过：{cnt.get('fail', 0)} 条（事实错误，须修正）")
    lines.append(f"- 待复核：{cnt.get('retry', 0)} 条（证据不足/调用失败，人工复核）")
    lines.append("")
    lines.append("## 二、不通过条目（事实错误明细，仅列 type=error）")
    lines.append("")
    fail_n = 0
    for r in results:
        if r["verdict"].get("decision") == "fail":
            e = errs(r["verdict"])
            if not e:
                e = r["verdict"].get("issues", [])  # 旧格式无 type 时全部展示
            fail_n += 1
            lines.append(f"### {r['ku_id']} ｜ {r['title']}（置信度={r['verdict'].get('confidence')}）")
            lines.append("")
            for iss in e:
                lines.append(f"- [{iss.get('field')}] {iss.get('problem')}")
                lines.append(f"  - 证据：{iss.get('evidence')}")
            lines.append("")
    if fail_n == 0:
        lines.append("无。")
    lines.append("")
    lines.append("## 三、待复核条目（人工复核队列）")
    lines.append("")
    retry_n = 0
    for r in results:
        if r["verdict"].get("decision") == "retry":
            retry_n += 1
            lines.append(f"- {r['ku_id']} ｜ {r['title']}：{'；'.join(i.get('problem','') for i in r['verdict'].get('issues', []))[:120]}")
    if retry_n == 0:
        lines.append("无。")
    lines.append("")
    lines.append("## 四、改进建议（通过条目附带，不阻断入库）")
    lines.append("")
    imp_n = 0
    for r in results:
        im = imps(r["verdict"])
        if im:
            imp_n += 1
            lines.append(f"- {r['ku_id']} ｜ {r['title']}")
            for iss in im:
                lines.append(f"  - [{iss.get('field')}] {iss.get('problem')}")
    if imp_n == 0:
        lines.append("无。")
    lines.append("")
    lines.append("## 五、验证者配置说明")
    lines.append("")
    lines.append(f"- 当前验证模型：{cfg['provider']}/{cfg['model']}（与生成模型{'同源' if cfg['provider']=='deepseek' else '不同供应商——真独立验证'}）")
    lines.append("- 切换第二家模型：在 .env 配置 SECOND_MODEL_BASE_URL / SECOND_MODEL_API_KEY / SECOND_MODEL 后重新运行本脚本，自动生效")
    lines.append("- 验证通过条目可将 verified_by 记录为 {\"model\": \"<验证模型>\", \"method\": \"layer2_independent\", \"date\": \"2026-08-04\"}")
    lines.append("")
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("报告已写入:", REPORT)
    print("汇总:", {("通过" if k == "pass" else "不通过" if k == "fail" else "待复核" if k == "retry" else "未知"): v for k, v in cnt.items()})


if __name__ == "__main__":
    main()
