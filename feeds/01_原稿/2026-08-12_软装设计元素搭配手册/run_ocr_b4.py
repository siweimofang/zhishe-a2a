# -*- coding: utf-8 -*-
import os, sys
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=False)
outdir = '批次4_PDF172-228'
for n in range(172, 187):
    src = f'rendered/p{n}.png'
    res = ocr.ocr(src, cls=True)
    lines = []
    if res and res[0]:
        for item in res[0]:
            box, (text, conf) = item
            ys = [p[1] for p in box]; xs = [p[0] for p in box]
            y = int(min(ys)); x = int(min(xs)); x1 = int(max(xs))
            lines.append(f'y={y} x={x} x1={x1} conf={conf:.2f} | {text}')
    out = os.path.join(outdir, f'ocr_raw_p{n}.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(n, len(lines), 'lines ->', out)
