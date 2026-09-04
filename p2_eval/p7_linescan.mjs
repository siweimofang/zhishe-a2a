// 残留丢行扫描: 每份转写逐行喂 parseQuoteText,
// 含数字(或"元")但解析不出的行 = 潜在残留丢失 → 打印供人工判读
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const PLUGIN = 'D:/知设Agent生态/千问AI Agent/zhishe-a2a/dsh-plugins/zhishe-baojia-shenhe';
const OUT = 'C:/Users/Administrator/.qoderworkcn/workspace/msklrypny7w2454t';
const parser = await import(pathToFileURL(`${PLUGIN}/lib/quote_parser.js`).href);

const files = ['q202_1049_r1.txt', 'q202_1049_r2.txt', 'q202_1137_r1.txt', 'q202_1217_r1.txt'];
for (const f of files) {
  const text = readFileSync(`${OUT}/${f}`, 'utf-8');
  const all = parser.parseQuoteText(text);
  const bad = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const hasNum = /\d/.test(line);
    if (!hasNum) continue;
    const got = parser.parseQuoteText(line);
    if (got.length === 0) bad.push(line);
  }
  console.log(`\n== ${f}: 全文解析=${all.length}条, 可疑丢行=${bad.length}`);
  for (const b of bad) console.log(`   | ${b.slice(0, 110)}`);
}
