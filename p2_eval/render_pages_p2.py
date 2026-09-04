# -*- coding: utf-8 -*-
"""P1分页送审: PDF→红档脱敏→按页独立PNG(__pNN命名)→eval_inbox; 旧拼接图归档"""
import fitz, os, shutil
from PIL import Image

SRC = r'F:\工作\2025年\2025.03.02首创光合城\预算'
INBOX = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\p2_eval\eval_inbox'
ARCH = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\p2_eval\results\stitched_0904'
os.makedirs(ARCH, exist_ok=True)

# 1) 旧拼接图移出inbox(归档, 不删)
for fn in os.listdir(INBOX):
    if '__p' not in fn:
        shutil.move(os.path.join(INBOX, fn), os.path.join(ARCH, fn))
        print('归档拼接图:', fn)

MASKS = {
    '基础工程合同.pdf': ['<姓名>', '<身份证号>'],
    '主材代购单.pdf':   ['<姓名>', '<手机号>', '<门店地址>'],
    '平品报价2025.3.5.pdf': [],
    '优品报价2025.3.5.pdf': [],
    '全屋定制报价.pdf': [],
}
DPI = {'基础工程合同.pdf': 180, '主材代购单.pdf': 150,
       '平品报价2025.3.5.pdf': 150, '优品报价2025.3.5.pdf': 150, '全屋定制报价.pdf': 180}
STEMS = {
    '基础工程合同.pdf': 'contract_101_jichu',
    '主材代购单.pdf': 'contract_102_zhucai_daigou',
    '平品报价2025.3.5.pdf': 'quote_201_pingpin',
    '优品报价2025.3.5.pdf': 'quote_202_youpin',
    '全屋定制报价.pdf': 'quote_203_dingzhi',
}

for fn, masks in MASKS.items():
    d = fitz.open(os.path.join(SRC, fn))
    stem = STEMS[fn]
    for i, page in enumerate(d, 1):
        for s in masks:
            for r in page.search_for(s):
                page.add_redact_annot(r)
        if masks:
            page.apply_redactions()
        residue = [s for s in masks if s in page.get_text()]
        pix = page.get_pixmap(dpi=DPI[fn])
        outp = os.path.join(INBOX, f'{stem}__p{i:02d}.png')
        Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(outp, optimize=True)
        assert not residue, f'{fn} p{i} PII残留: {residue}'
        print(f'{stem}__p{i:02d}.png  {pix.width}x{pix.height}  {os.path.getsize(outp)//1024}KB')
    d.close()
print('DONE')
