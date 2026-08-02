"""
备案材料一键打包 + 加密脚本
============================
功能:
1. 收集 4 份算法备案 PDF(Mavis 已生成)
2. 等 User 拍 3 份证照 PDF
3. 全部打包成加密 ZIP
4. 报告 User 准备状态

作者:Mavis 2026-06-26 10:15
"""
import os
import pyzipper
from datetime import datetime

BASE = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\备案'
OUT_DIR = os.path.join(BASE, '备案材料')
ZIP_OUT = os.path.join(BASE, f'V1.3_备案_全部7份材料_加密_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')

# 4 份算法备案材料(Mavis 自动转)
ALGO_PDFS = [
    'V1.3_算法备案_承诺书.pdf',
    'V1.3_算法备案_主体责任落实情况.pdf',
    'V1.3_算法备案_自评估报告_框架.pdf',
    'V1.3_算法安全责任人工作证明.pdf',
]

# 3 份 User 必拍
USER_PDFS = [
    'yezhizhao_zhishi_2025.pdf',
    'shenfenzheng_zhengmian.pdf',
    'shenfenzheng_fanmian.pdf',
]

ALL_7 = ALGO_PDFS + USER_PDFS

# 备案专用密码(跟加密算法备案 4 份相同 + 加 ICP 后缀)
PASSWORD = 'MzN2026@ZhisheBeiAn7Files'

print('=' * 80)
print('备案材料一键打包 + 加密')
print('=' * 80)

# 检查 7 份
print(f'\n输出 ZIP:{ZIP_OUT}')
print(f'密码:{PASSWORD}')
print()

# 状态
algo_ok = []
algo_missing = []
for f in ALGO_PDFS:
    p = os.path.join(OUT_DIR, f)
    if os.path.exists(p):
        size = os.path.getsize(p)
        algo_ok.append((f, size))
        print(f'  ✅ {f} ({size} 字节)')
    else:
        algo_missing.append(f)
        print(f'  ❌ {f} 缺失')

print()
user_ok = []
user_missing = []
for f in USER_PDFS:
    p = os.path.join(OUT_DIR, f)
    if os.path.exists(p):
        size = os.path.getsize(p)
        user_ok.append((f, size))
        print(f'  ✅ {f} ({size} 字节)')
    else:
        user_missing.append(f)
        print(f'  ❌ {f} 缺失(User 必拍)')

# 打包
print()
if not algo_missing and not user_missing:
    print('=== 7 份齐全,开始加密打包 ===')
    with pyzipper.AESZipFile(ZIP_OUT, 'w',
                              compression=pyzipper.ZIP_LZMA,
                              encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(PASSWORD.encode('utf-8'))
        for f in ALL_7:
            p = os.path.join(OUT_DIR, f)
            if os.path.exists(p):
                zf.write(p, arcname=f)
                print(f'  [加密] {f}')

    size = os.path.getsize(ZIP_OUT)
    print()
    print(f'✅ 加密 ZIP:{size} 字节')
    print(f'路径:{ZIP_OUT}')
    print()
    print('=== User 操作 ===')
    print('1. 存到密码管理器(1Password / Bitwarden)')
    print('2. 备案系统上传:解压 → 选 7 份 PDF → 上传')
    print('3. 备案完保留 ZIP(防本机丢失)')
elif algo_missing:
    print('=== 错误:算法备案 4 份 PDF 不全 ===')
    print('请跑:python convert_7_to_pdf.py')
else:
    print('=== 等 User 拍 3 份证照 ===')
    print()
    print('User 必拍步骤:')
    print('1. 用"全能扫描王"APP')
    print('2. 拍 3 张:营业执照 + 身份证正面 + 身份证反面')
    print('3. 输出 PDF,存到以下 3 个路径:')
    for f in user_missing:
        p = os.path.join(OUT_DIR, f)
        print(f'   {p}')
    print()
    print('4. 拍完跑本脚本(本脚本):自动打包 + 加密')

print()
print('=' * 80)
print('总览')
print('=' * 80)
print(f'算法备案 4 份 PDF:已转 {len(algo_ok)}/4')
print(f'User 必拍 3 份:已有 {len(user_ok)}/3')
print(f'总计:已就绪 {len(algo_ok) + len(user_ok)}/7')
