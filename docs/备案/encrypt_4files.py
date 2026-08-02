"""
加密压缩 4 份算法备案材料
铁律 21(2026-06-26 09:44 立):User 5 项数据 + 4 份材料加密压缩
用法:
  python encrypt_4files.py
"""
import os
import pyzipper
from datetime import datetime

BASE = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\备案'
FILES = [
    'V1.3_算法备案_承诺书.md',
    'V1.3_算法备案_主体责任落实情况.md',
    'V1.3_算法备案_自评估报告_框架.md',
    'V1.3_算法安全责任人工作证明.md',
]

# 密码:User 拍板"需要时调用",Mavis 拼一个 User 易记的密码
# 组成:法人姓名 + 备案日期 + Zhishe
PASSWORD = 'MzN2026@ZhisheBeiAn'

OUT = os.path.join(BASE, f'V1.3_算法备案_4份材料_加密_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')

print('=' * 80)
print('加密压缩 4 份算法备案材料')
print('=' * 80)
print(f'密码:{PASSWORD}')
print(f'输出:{OUT}')
print()

# pyzipper 创建 AES 加密 ZIP
with pyzipper.AESZipFile(OUT, 'w',
                          compression=pyzipper.ZIP_LZMA,
                          encryption=pyzipper.WZ_AES) as zf:
    zf.setpassword(PASSWORD.encode('utf-8'))
    for f in FILES:
        full = os.path.join(BASE, f)
        if os.path.exists(full):
            zf.write(full, arcname=f)
            print(f'  [加密] {f} ({os.path.getsize(full)} 字节)')
        else:
            print(f'  [跳过] {f} 不存在')

print()
print(f'加密 ZIP:{os.path.getsize(OUT)} 字节')
print(f'路径:{OUT}')
print()
print('=' * 80)
print('User 必看')
print('=' * 80)
print(f'密码:{PASSWORD}')
print(f'建议:把密码存到密码管理器(1Password / Bitwarden / LastPass)')
print(f'解压:7-Zip / WinRAR / 系统资源管理器 都能打开')
print(f'用途:')
print(f'  1. 备案后存到本机,加密防泄露')
print(f'  2. 提交备案系统时:解压 → 转 PDF → 上传工信部')
print(f'  3. 1-3 个月备案审核期间,本机不存明文(铁律 21)')
