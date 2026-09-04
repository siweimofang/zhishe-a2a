#!/usr/bin/env node
/**
 * benchmark_draft.mjs - 批次三/短板④工具侧: 基准价条目草稿生成器
 *
 * 从人工确认过的真值库(truth_quote.csv, 156行)自动抽出基准价草稿行——
 * 新增候选(基准库未覆盖) / 校准建议(观察价偏离基准区间) / 基准内(统计不列行)。
 * 每行带出处(source_samples), 满足第九节铁律: 真实样张提炼、出处可追溯。
 *
 * 红线: 只产草稿, 绝不自动写 benchmark.json——人审(补单位/砍行/改价)后另行入库;
 *       真值库无单位列, 草稿 unit 留空由人审补填, 价对建议均标"纲需人工判"。
 *
 * 用法:
 *   node benchmark_draft.mjs                          # 全量真值库
 *   node benchmark_draft.mjs --city 沈阳 --tier 中档  # 价区按城市/档次系数换算
 *   node benchmark_draft.mjs --truth truth_quote.csv  # 指定真值文件
 *
 * 输出: results/benchmark_draft_<TS>/draft.md + draft.csv
 * 口径: #r1/#r2 重复轮次去重(同轮价格不一致则旗标); 同名跨样张取中位数/最小/最大;
 *       匹配=双向子串+基准关键词(P6教训: 泛短名碰撞只旗标不自动合并, 合并留人审)。
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { loadBenchmark, adjustPriceRange } from '../dsh-plugins/zhishe-baojia-shenhe/lib/engines/anomaly_engine.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const argOf = (f, d) => { const i = args.indexOf(f); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const TRUTH = argOf('--truth', 'truth_quote.csv');
const CITY = argOf('--city', '沈阳');
const TIER = argOf('--tier', '中档');
const TS = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12);

// ---- 极简CSV解析(带引号容错) ----
function parseCsv(text) {
    const rows = [];
    let row = [], field = '', inQ = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (inQ) {
            if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
            else if (c === '"') inQ = false;
            else field += c;
        } else if (c === '"') inQ = true;
        else if (c === ',') { row.push(field); field = ''; }
        else if (c === '\n' || c === '\r') {
            if (c === '\r' && text[i + 1] === '\n') i++;
            row.push(field); field = '';
            if (row.some(v => v !== '')) rows.push(row);
            row = [];
        } else field += c;
    }
    if (field !== '' || row.length) { row.push(field); if (row.some(v => v !== '')) rows.push(row); }
    const head = rows[0].map(h => h.replace(/^\uFEFF/, ''));
    return rows.slice(1).map(r => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}

// ---- 单位归一(P7守卫同源词表, 仅用于基准侧展示) ----
const UNIT_NORM = { '㎡': '㎡', 'm²': '㎡', '平米': '㎡', '平方米': '㎡', '平': '㎡', 'm': 'm', '米': 'm', '延米': 'm' };
const normUnit = (u) => { const r = String(u || '').trim().replace(/^元\//, ''); return UNIT_NORM[r] || r; };
const toNum = (v) => { const n = Number(String(v ?? '').replace(/[元,]/g, '').trim()); return Number.isFinite(n) ? n : null; };

// ---- 读取真值并去重(#r重复轮) ----
const truthPath = join(HERE, TRUTH);
if (!existsSync(truthPath)) { console.error(`真值文件不存在: ${truthPath}`); process.exit(1); }
const rows = parseCsv(readFileSync(truthPath, 'utf8'));
const perSample = new Map(); // (基样张, 真值名) → [{price, sample_id, is_pit, pit_type}]
let skipped = 0, priceConflict = 0;
for (const r of rows) {
    const name = String(r.truth_entry || '').trim();
    const price = toNum(r.truth_price);
    if (!name || name.length < 2 || price === null) { skipped++; continue; }
    const base = String(r.sample_id || '').split('#')[0];
    const key = `${base}|${name}`;
    if (!perSample.has(key)) perSample.set(key, { name, base, prices: [], pits: new Set(), sample_ids: new Set() });
    const g = perSample.get(key);
    if (!g.prices.includes(price)) g.prices.push(price);
    g.sample_ids.add(base);
    if (String(r.is_pit) === '1') { g.pits.add(String(r.pit_type || '坑')); }
    if (g.prices.length > 1) priceConflict++;
}
const samples = [...new Set([...perSample.values()].map(g => g.base))].sort();
console.log(`真值: ${rows.length}行 → 去重后 ${perSample.size} 组(样张 ${samples.join(',')}; 跳过空价/空名 ${skipped}; 同组多价旗标 ${priceConflict})`);

// ---- 基准库索引 ----
const benchmark = loadBenchmark();
const flat = [];
for (const [cat, items] of Object.entries(benchmark.items)) {
    for (const [name, spec] of Object.entries(items)) {
        flat.push({ cat, name, spec, kws: spec.keywords || [] });
    }
}
function matchBenchmark(truthName) {
    const hits = flat.filter(it =>
        it.name === truthName || it.name.includes(truthName) || truthName.includes(it.name)
        || it.kws.some(k => truthName.includes(k) || k.includes(truthName)));
    return hits;
}
const median = (arr) => { const s = [...arr].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

// ---- 分类: 新增候选 / 校准建议 / 基准内 ----
const draft = [];
const within = [];
for (const g of perSample.values()) {
    const hits = matchBenchmark(g.name);
    const pMed = median(g.prices), pMin = Math.min(...g.prices), pMax = Math.max(...g.prices);
    const base = {
        truth_name: g.name, unit: '', // 真值库无单位列——人审补填
        price_median: pMed, price_min: pMin, price_max: pMax,
        sample_count: g.sample_ids.size, sources: [...g.sample_ids].join('+'),
        pit: [...g.pits].join(',') || '',
    };
    if (hits.length === 0) {
        draft.push({ action: '新增候选', ...base, matched_category: '', matched_name: '', benchmark_unit: '', benchmark_range: '', note: '基准库无此名/关键词, 人审定类目+单位后可入库' });
        continue;
    }
    const it = hits[0];
    const range = adjustPriceRange(it.spec, CITY, TIER, benchmark);
    const ambiguous = hits.length > 1 ? `⚠多命中(${hits.map(h => h.name).join('/')})需人工消歧` : '';
    const unitB = normUnit(it.spec.unit);
    const out = {
        action: '', ...base,
        matched_category: it.cat, matched_name: it.name, benchmark_unit: it.spec.unit,
        benchmark_range: `${range.min}-${range.max}${it.spec.unit || ''}`, note: ambiguous,
    };
    if (pMed >= range.min && pMed <= range.max) {
        out.action = '基准内'; within.push(out);
    } else {
        const dir = pMed > range.max ? '高于' : '低于';
        const edge = pMed > range.max ? range.max : range.min;
        const dev = Math.round(Math.abs(pMed - edge) / edge * 1000) / 10;
        out.action = '校准建议';
        // P7守卫同源启发: 偏离>100%几乎必是纲错配(元/片vs元/㎡, 总额vs费率)——旗标供人审快速分诊, 不自动判
        const suspect = dev > 100 ? '疑似纲错配, ' : '';
        out.note = [out.note, `${suspect}观察中位${dir}基准边缘${dev}%(纲需人工判: 真值无单位列)`].filter(Boolean).join('; ');
        draft.push(out);
    }
}
// 多价旗标并入note
for (const d of draft) {
    const g = [...perSample.values()].find(x => x.name === d.truth_name);
    if (g && g.prices.length > 1) d.note = [d.note, `同组多价${g.prices.join('/')}需核对`].filter(Boolean).join('; ');
}

// ---- 输出 ----
const outDir = join(HERE, 'results', `benchmark_draft_${TS}`);
mkdirSync(outDir, { recursive: true });
const csvHead = 'action,truth_name,unit,price_median,price_min,price_max,sample_count,sources,pit,matched_category,matched_name,benchmark_unit,benchmark_range,note';
const esc = (v) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const csv = [csvHead, ...draft.map(d => [d.action, d.truth_name, d.unit, d.price_median, d.price_min, d.price_max, d.sample_count, d.sources, d.pit, d.matched_category, d.matched_name, d.benchmark_unit, d.benchmark_range, d.note].map(esc).join(','))].join('\n');
writeFileSync(join(outDir, 'draft.csv'), '\uFEFF' + csv + '\n', 'utf8');

const stat = (a) => draft.filter(d => d.action === a).length;
const md = [
    `# 基准价草稿(人审用) ${TS}`,
    ``,
    `来源: ${TRUTH}(${rows.length}行→去重${perSample.size}组) | 真值口径: ${CITY}/${TIER} | 样张: ${samples.join(',')}`,
    `**红线: 本文件是草稿, 不自动写 benchmark.json——人审补单位/定类目/砍行后方可入库**`,
    ``,
    `| 动作 | 条数 |`,
    `|---|---|`,
    `| 新增候选(基准库未覆盖) | ${stat('新增候选')} |`,
    `| 校准建议(观察价偏离区间) | ${stat('校准建议')} |`,
    `| 基准内(仅统计,不列行) | ${within.length} |`,
    ``,
    `## 新增候选(${stat('新增候选')})`,
    ``,
    `| 真值名 | 单位(补填) | 中位 | 最小~最大 | 样张数 | 出处 | 坑 |`,
    `|---|---|---|---|---|---|---|`,
    ...draft.filter(d => d.action === '新增候选').map(d => `| ${d.truth_name} | | ${d.price_median} | ${d.price_min}~${d.price_max} | ${d.sample_count} | ${d.sources} | ${d.pit || '-'} |`),
    ``,
    `## 校准建议(${stat('校准建议')})`,
    ``,
    `| 真值名 | 观察中位 | 基准区间(${CITY}/${TIER}) | 基准项 | 样张数 | 出处 | 说明 |`,
    `|---|---|---|---|---|---|---|`,
    ...draft.filter(d => d.action === '校准建议').map(d => `| ${d.truth_name} | ${d.price_median} | ${d.benchmark_range} | ${d.matched_category}/${d.matched_name} | ${d.sample_count} | ${d.sources} | ${d.note || '-'} |`),
    ``,
    `## 入库步骤(人审后)`,
    `1. 补填新增候选的单位列, 定类目; 校准建议逐条核对是否真偏离(先查纲, 再查舍入——P2坑③)`,
    `2. 确认行写入 benchmark.json 新版本(version递增, last_updated, note记录出处批次)`,
    `3. 跑 npm test + 一次 resplice 回归确认无劣化`,
].join('\n');
writeFileSync(join(outDir, 'draft.md'), md, 'utf8');
console.log(`\n草稿已生成: ${outDir}`);
console.log(`新增候选 ${stat('新增候选')} | 校准建议 ${stat('校准建议')} | 基准内 ${within.length}(不列行)`);
console.log('⚠ 红线: 草稿仅供人审, 未触碰 benchmark.json');
