/**
 * P2 Step3 评测执行器：批量跑插件四工具，输出 JSON 结果集
 * 用法: node eval_runner.mjs <jobs.json> <results.json>
 * jobs.json: [{ "id": "contract_synth_001", "tool": "hetong_shenhe", "args": { "contract_images": ["D:/x.png"] } }]
 * 环境变量: DEEPSEEK_API_KEY（图片路径必需；未配置时工具返回优雅降级 error，结果照记）
 */
import { pathToFileURL } from 'url';
import fs from 'node:fs';

const LIB = 'D:\\知设Agent生态\\千问AI Agent\\zhishe-a2a\\dsh-plugins\\zhishe-baojia-shenhe\\lib';
const [, , jobsPath, outPath] = process.argv;
if (!jobsPath || !outPath) {
    console.error('用法: node eval_runner.mjs <jobs.json> <results.json>');
    process.exit(1);
}

const idx = await import(pathToFileURL(LIB + '\\index.js').href);
const tools = idx.apply();
const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
const out = [];
for (const j of jobs) {
    const t0 = Date.now();
    let r;
    try {
        r = await tools[j.tool](j.args || {});
    } catch (e) {
        r = { status: 'exception', message: String((e && e.message) || e) };
    }
    const ms = Date.now() - t0;
    out.push({ id: j.id, tool: j.tool, ms, result: r });
    console.error(`[${j.id}] ${j.tool} -> ${r.status} ${ms}ms`);
}
fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.error(`DONE ${out.length} jobs -> ${outPath}`);
