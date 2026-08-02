# -*- coding: utf-8 -*-
from PIL import Image

src = r'E:\小红书\学习AI大模型如何应用\千问AI Agent\微信图片_2026-05-18_231603_306.png'
dst = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\zhishe_avatar.png'

img = Image.open(src)
print(f'原图: format={img.format} size={img.size} mode={img.mode}')

# RGBA 模式转 RGB(PNG 透明通道在某些平台会变黑底)
if img.mode in ('RGBA', 'LA', 'P'):
    bg = Image.new('RGB', img.size, (255, 255, 255))
    if img.mode == 'P':
        img = img.convert('RGBA')
    bg.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
    img = bg
elif img.mode != 'RGB':
    img = img.convert('RGB')

# 1:1 居中裁剪
w, h = img.size
side = min(w, h)
left = (w - side) // 2
top = (h - side) // 2
img = img.crop((left, top, left + side, top + side))
print(f'裁剪后: {img.size}')

# 缩放到 256x256(腾讯元器要求)
out = img.resize((256, 256), Image.LANCZOS)
out.save(dst, 'PNG', optimize=True)
print(f'输出: {dst}')

import os
print(f'大小: {os.path.getsize(dst)} 字节')
