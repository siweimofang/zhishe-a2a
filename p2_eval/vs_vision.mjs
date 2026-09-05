#!/usr/bin/env node
/**
 * vs_vision.mjs - v0.5.0 双供应商×双模式 对拍脚手架(短板①②验收工具)
 *
 * 用法:
 *   node vs_vision.mjs                          # 结构化模式×[deepseek,bailian]
 *   node vs_vision.mjs --mode text              # 文本路径基线(对拍召回基线用)
 *   node vs_vision.mjs --dir ../eval_inbox --providers deepseek
 *   node vs_vision.mjs --city 沈阳 --tier 中档
 *
 * 样张约定(与 prefill_p2.py 一致): quote_*.jpg/png, 多页用 __pN 后缀(quote_201__p1.png...)
 *
 * 输出: results/vs_vision_<TS>/summary.json + summary.md
 *   每样张×供应商: 提取成功/JSON解析失败/条目数/审核四态统计/跨页重复警示
 *   汇总: 各供应商平均条目数/unknown率(结构化模式的单位缺失/单价缺失透明可见)
 *
 * 密钥: 从 ../.env 读取 DEEPSEEK_API_KEY / BAILIAN_API_KEY / BAILIAN_VL_MODEL(也可环境变量)
 * 成本: 单图 384 tokens Flash 级, 全量 5 样张×2 供应商 < 0.2 元(估)
 * 注意: 样张属客户数据, 只进 results/(已gitignore), 不入库
 */
import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { extname, join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { extractQuoteStructuredFromImages, extractQuoteFromImages } from '../dsh-plugins/zhishe-baojia-shenhe/lib/vision/quote_ocr.js';
import { parseItemsFromStructured, parseQuoteText } from '../dsh-plugins/zhishe-baojia-shenhe/lib/quote_parser.js';
import { auditQuote } from '../dsh-plugins/zhishe-baojia-shenhe/lib/engines/anomaly_engine.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const A2A = dirname(HERE);
const EXTS = ('.png,.jpg,.jpeg,.webp,.bmp').split(',');

// ---- args ----
const args = process.argv.slice(2);
function argOf(flag, def) {
    const i = args.indexOf(flag);
    return i >= 0 && args[i + 1] ? args[i + 1] : def;
}
const DIR = argOf('--dir', join(A2A, 'eval_inbox'));
const MODE = argOf('--mode', 'structured'); // structured | text
const PROVIDERS = argOf('--providers', 'deepseek,bailian').split(',').map(s => s.trim()).filter(Boolean);
const CITY = argOf('--city', '沈阳');
const TIER = argOf('--tier', '中档');
const TS = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12);

// ---- env ----
const envFile = join(A2A, '.env');
if (existsSync(envFile)) {
    for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
        const m = line.match(/^(DEEPSEEK_API_KEY|BAILIAN_API_KEY|BAILIAN_VL_MODEL|VISION_PROVIDER)=(.*)$/);
        if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^"|"$/g, '');
    }
}

// ---- 样张分组(同 prefill_p2: __pN 分页合并) ----
function scanSamples(d) {
    if (!existsSync(d)) return { samples: [], skipped: 0, missing: true };
    const groups = new Map();
    let skipped = 0;
    for (const fn of readdirSync(d).sort()) {
        if (!EXTS.includes(extname(fn).toLowerCase())) continue;
        if (!/^quote_/i.test(fn)) { skipped++; continue; }
        const stem = fn.replace(/\.[^.]+$/, '');
        const m = stem.match(/^(.*?)__p(\d+)$/i);
        const gkey = m ? m[1] : stem;
        if (!groups.has(gkey)) groups.set(gkey, []);
        groups.get(gkey).push({ pageno: m ? Number(m[2]) : 0, path: join(d, fn) });
    }
    const samples = [...groups.entries()]
        .map(([id, imgs]) => ({ id, images: imgs.sort((a, b) => a.pageno - b.pageno).map(x => x.path) }))
        .sort((a, b) => a.id.localeCompare(b.id));
    return { samples, skipped, missing: false };
}

// ---- 单样张单供应商跑一组 ----
async function runOne(sample, provider, mode) {
    process.env.VISION_PROVIDER = provider;
    let extraction, items, text = null, modeUsed = mode;
    if (mode === 'structured') {
        extraction = await extractQuoteStructuredFromImages(sample.images);
        if (extraction.success) {
            items = parseItemsFromStructured(extraction.data.items);
        } else if (extraction.fallback_to_text) {
            // 回退文本路径(与插件生产逻辑一致), 记录回退事实
            modeUsed = 'text(fallback)';
            text = extraction.raw_text;
            extraction = { success: true, text, provider: extraction.provider, model: extraction.model };
        }
    } else {
        extraction = await extractQuoteFromImages(sample.images);
    }
    if (!items && extraction?.success) items = parseQuoteText(extraction.text);
    if (!extraction?.success || !items) {
        return { sample: sample.id, provider, mode: modeUsed, ok: false, error: extraction?.error || '提取失败' };
    }
    const report = auditQuote(items, { city: CITY, tier: TIER });
    return {
        sample: sample.id, provider, mode: modeUsed, ok: true,
        provider_actual: extraction.provider, model: extraction.model,
        pages: extraction.pages_total || sample.images.length,
        items_extracted: items.length,
        // v0.6.0 批次六: 条目明细落盘(召回对拍需要名字/单价, summary.md 表格不展示)
        items: items.map(x => ({ name: String(x.name || ''), unit: x.unit ?? null, qty: x.quantity ?? null, unit_price: x.unit_price ?? null, total_price: x.total_price ?? null })),
        ...(extraction.json_parse_failures != null && { json_parse_failures: extraction.json_parse_failures }),
        ...(extraction.data?.duplicate_warnings?.length && { duplicate_groups: extraction.data.duplicate_warnings.length }),
        ...(extraction.ocr_warnings?.length && { ocr_warning_groups: extraction.ocr_warnings.length }),
        audit_ok: !!report.success,
        ...(report.success && {
            pass: report.stats.pass,
            warning_high: report.stats.warning_high,
            warning_low: report.stats.warning_low,
            unknown: report.stats.unknown,
            missing: report.stats.missing_items,
            unknown_labels: report.results.filter(r => r.status === 'unknown').map(r => r.risk?.label).join('/') || '-',
        }),
        usage: extraction.usage || null,
        offpeak: extraction.offpeak ? extraction.offpeak.offpeak : null, // v0.5.1 批次二: 峰谷标记入行
    };
}

// ---- main ----
const { samples, skipped, missing } = scanSamples(DIR);
console.log(`对拍配置: mode=${MODE} providers=[${PROVIDERS.join(',')}] city=${CITY} tier=${TIER}`);
if (missing || samples.length === 0) {
    console.log(`\n⚠️ 未找到样张: ${DIR} ${missing ? '(目录不存在)' : '(无 quote_*.jpg/png)'}——脚手架就绪, 样张进站后重跑即可`);
    console.log('样张命名: quote_<样本>__p1.png..__pN.png (与 prefill_p2.py 同约定)');
    process.exit(0);
}
console.log(`样张 ${samples.length} 组(另跳过 ${skipped} 个非报价文件)\n`);

const rows = [];
for (const provider of PROVIDERS) {
    for (const sample of samples) {
        process.stdout.write(`  ${provider} × ${sample.id} (${sample.images.length}页) ... `);
        try {
            const row = await runOne(sample, provider, MODE);
            rows.push(row);
            console.log(row.ok
                ? `${row.items_extracted}条 pass=${row.pass} warnH=${row.warning_high} warnL=${row.warning_low} unknown=${row.unknown} missing=${row.missing}${row.mode !== MODE ? ` [${row.mode}]` : ''}`
                : `失败: ${row.error?.slice(0, 80)}`);
        } catch (err) {
            rows.push({ sample: sample.id, provider, ok: false, error: err.message });
            console.log(`异常: ${err.message.slice(0, 80)}`);
        }
    }
}

// 供应商配置缺失的说明行
for (const p of PROVIDERS) {
    if (p === 'bailian' && (!process.env.BAILIAN_API_KEY || !process.env.BAILIAN_VL_MODEL)) {
        console.log(`\nℹ️ bailian 路线需 BAILIAN_API_KEY + BAILIAN_VL_MODEL(.env 或环境变量), 未配置则该路线结果为失败行`);
    }
}

// ---- 汇总 ----
const outDir = join(HERE, 'results', `vs_vision_${TS}`);
mkdirSync(outDir, { recursive: true });
const summary = { ts: TS, mode: MODE, city: CITY, tier: TIER, providers: PROVIDERS, samples: samples.map(s => s.id), rows };
writeFileSync(join(outDir, 'summary.json'), JSON.stringify(summary, null, 2));

const okRows = rows.filter(r => r.ok && r.audit_ok);
const md = [
    `# vs_vision 对拍 ${TS}`,
    ``,
    `mode=${MODE} | city=${CITY} | tier=${TIER} | 样张=${samples.length} | providers=${PROVIDERS.join('/')}`,
    ``,
    `| 供应商 | 样张 | 模式 | 条目 | pass | 警高 | 警低 | unknown | 缺项 | 备注 |`,
    `|---|---|---|---|---|---|---|---|---|---|`,
    ...rows.map(r => r.ok && r.audit_ok
        ? `| ${r.provider} | ${r.sample} | ${r.mode} | ${r.items_extracted} | ${r.pass} | ${r.warning_high} | ${r.warning_low} | ${r.unknown} | ${r.missing} | ${[r.json_parse_failures ? `json失败${r.json_parse_failures}` : '', r.duplicate_groups ? `重复组${r.duplicate_groups}` : '', r.ocr_warning_groups ? `复读组${r.ocr_warning_groups}` : ''].filter(Boolean).join(',') || '-'} |`
        : `| ${r.provider} | ${r.sample} | ${r.mode || '?'} | - | - | - | - | - | - | ❌ ${String(r.error).slice(0, 60)} |`),
    ``,
    `## 汇总(审核成功行)`,
    ...PROVIDERS.map(p => {
        const rs = okRows.filter(r => r.provider === p);
        if (!rs.length) return `- ${p}: 无成功行`;
        const avg = k => (rs.reduce((s, r) => s + r[k], 0) / rs.length).toFixed(1);
        return `- ${p}: 平均条目 ${avg('items_extracted')} | unknown率 ${avg('unknown')}/${avg('items_extracted')} | 警 ${avg('warning_high') + avg('warning_low')} | 缺项 ${avg('missing')}`;
    }),
    ``,
    `验收口径(补足方案§3短板②): 结构化模式召回不低于文本基线(0904基线 82.1%召回/45.3%价对), unknown率透明可解释即合格。`,
].join('\n');
writeFileSync(join(outDir, 'summary.md'), md);
console.log(`\n结果已存: ${outDir}/summary.md + summary.json`);
