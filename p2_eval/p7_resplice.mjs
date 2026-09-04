// 离线重拼 prefill 批次: 对指定 job(或全部 quote_*) 用
// 存储OCR文本 + 新解析器(词表含延米/片) + auditQuote(含0904单位错配守卫)
// 只重算 report.{results, missing_items, stats, overall, input_items, extraction_quality}, 其余字段保持原样
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const HERE = 'D:/知设Agent生态/千问AI Agent/zhishe-a2a/p2_eval';
const PLUGIN = 'D:/知设Agent生态/千问AI Agent/zhishe-a2a/dsh-plugins/zhishe-baojia-shenhe';
const TS = process.argv[2] || '1217';
const JID = process.argv[3] || 'all';
const SRC = `${HERE}/results/prefill_0904_${TS}.json`;
const DST = `${HERE}/results/prefill_0904_${TS}_resplice.json`;

const engine = await import(pathToFileURL(`${PLUGIN}/lib/engines/anomaly_engine.js`).href);

const jobs = JSON.parse(readFileSync(SRC, 'utf-8'));
const targets = JID === 'all' ? jobs.filter(j => j.id.startsWith('quote_')) : jobs.filter(j => j.id === JID);
if (!targets.length) { console.error('no target jobs'); process.exit(1); }

for (const job of targets) {
  const result = job.result || {};
  const rep = result.report || {};
  const text = ((result.ocr || {}).extracted_text) || '';
  if (!text) { console.error(`${job.id}: OCR text missing, skip`); continue; }
  const warnBefore = (rep.results || []).filter(r => String(r.status).startsWith('warning')).length;
  const city = rep.city || '沈阳';
  const tier = rep.tier || '中档';
  const out = engine.auditQuote(text, { city, tier });
  if (!out.success) { console.error(`${job.id}: auditQuote failed: ${out.error}`); continue; }

  const newRep = { ...rep };
  newRep.results = out.results;
  newRep.missing_items = out.missing_items;
  newRep.stats = out.stats;
  newRep.overall = out.overall;
  newRep.input_items = out.input_items;
  newRep.extraction_quality = {
    lines_extracted: out.lines_extracted ?? null,
    entries_parsed: out.input_items,
    source: 'offline_resplice_0904',
  };
  result.report = newRep;

  const warnAfter = out.results.filter(r => String(r.status).startsWith('warning'));
  console.log(`${job.id}: 条目 ${(rep.results || []).length}→${out.results.length}, 警告 ${warnBefore}→${warnAfter.length}, unknown=${out.stats.unknown}, 漏项=${out.missing_items.length}`);
  for (const w of warnAfter) console.log(`    ${w.item} @${w.unit_price}${w.unit} → ${w.status}`);
}

writeFileSync(DST, JSON.stringify(jobs, null, 1), 'utf-8');
console.log(`写出: ${DST}`);
