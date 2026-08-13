# -*- coding: utf-8 -*-
import io, sys
from PIL import Image
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=False)
names = ['p184_label1','p184_label2','p184_label3','p184_blabel1','p184_blabel2','p184_blabel3',
         'p186_capL','p186_capR','p186_capR2','p180_capLm','p181_capL']
out = []
for n in names:
    im = Image.open(f'crops_b4/{n}.png').convert('L')
    w, h = im.size
    im = im.resize((w*3, h*3), Image.LANCZOS)
    tmp = f'_tmp_verify_{n}.png'
    im.save(tmp)
    res = ocr.ocr(tmp, cls=True)
    line = f'== {n} =='
    if res and res[0]:
        for r in res[0]:
            line += '\n' + str(r[1][0]) + ' conf=' + format(r[1][1], '.3f')
    else:
        line += '\n(no text)'
    out.append(line)
    import os
    os.remove(tmp)
with open('crops_b4/verify_labels.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
