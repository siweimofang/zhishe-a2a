"""
7 份备案材料 .md → .pdf 转换脚本(3 方案)
====================================
备案材料清单:
1. V1.3_算法备案_承诺书.md
2. V1.3_算法备案_主体责任落实情况.md
3. V1.3_算法备案_自评估报告_框架.md
4. V1.3_算法安全责任人工作证明.md

User 必拍 3 份:
5. 营业执照副本 PDF(User 用扫描王拍)
6. 法人身份证正面 PDF(User 拍)
7. 法人身份证反面 PDF(User 拍)

转换方法(Mavis 自动选 + User 拍板):
- 方案 A:pandoc + wkhtmltopdf(全自动,User 不用动手)
- 方案 B:Python markdown + reportlab(全自动)
- 方案 C:VS Code 插件 Markdown PDF(半自动)

作者:Mavis 2026-06-26 10:13
"""
import os
import sys
import subprocess
import shutil
from datetime import datetime

BASE = r'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\备案'
OUT_DIR = os.path.join(BASE, '备案材料')

# 4 份算法备案材料
ALGO_FILES = [
    'V1.3_算法备案_承诺书.md',
    'V1.3_算法备案_主体责任落实情况.md',
    'V1.3_算法备案_自评估报告_框架.md',
    'V1.3_算法安全责任人工作证明.md',
]

# User 必拍 3 份
USER_PDFS = [
    'yezhizhao_zhishi_2025.pdf',  # 营业执照
    'shenfenzheng_zhengmian.pdf',  # 身份证正面
    'shenfenzheng_fanmian.pdf',  # 身份证反面
]

ALL_7 = ALGO_FILES + USER_PDFS

def check_pandoc():
    """检查 pandoc 是否安装"""
    try:
        result = subprocess.run(['pandoc', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            return True, version
    except FileNotFoundError:
        pass
    return False, None

def check_wkhtmltopdf():
    """检查 wkhtmltopdf 是否安装"""
    common = [
        r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'C:\Program Files (x86)\wkhtmltopdf\wkhtmltopdf.exe',
    ]
    for p in common:
        if os.path.exists(p):
            return True, p
    return False, None

def check_python_pdf():
    """检查 Python PDF 库"""
    libs = ['reportlab', 'markdown', 'weasyprint', 'pdfkit']
    available = []
    for lib in libs:
        try:
            __import__(lib)
            available.append(lib)
        except ImportError:
            pass
    return available

def method_a_pandoc():
    """方案 A:pandoc + wkhtmltopdf"""
    pandoc_ok, _ = check_pandoc()
    wkhtml_ok, _ = check_wkhtmltopdf()
    if not pandoc_ok:
        return False, 'pandoc 未安装'
    if not wkhtml_ok:
        return False, 'wkhtmltopdf 未安装'
    return True, 'pandoc + wkhtmltopdf 全自动'

def method_b_python():
    """方案 B:Python markdown + reportlab"""
    libs = check_python_pdf()
    if 'reportlab' in libs and 'markdown' in libs:
        return True, 'Python reportlab + markdown'
    return False, f'Python 库缺失,可用:{libs}'

def method_c_manual():
    """方案 C:VS Code 插件"""
    return True, 'VS Code Markdown PDF 插件(半自动,User 操作)'

def convert_with_pandoc(md_path, pdf_path):
    """pandoc 转 PDF"""
    try:
        result = subprocess.run([
            'pandoc', md_path,
            '-o', pdf_path,
            '--pdf-engine=wkhtmltopdf',
            '-V', 'geometry:margin=1in',
            '--toc',
        ], capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        return False

def convert_with_python(md_path, pdf_path):
    """Python reportlab 转 PDF"""
    try:
        import markdown
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html = markdown.markdown(md_content, extensions=['extra', 'codehilite'])
        # 简化:用 reportlab 直接输出文字
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        for line in md_content.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 12))
            elif line.startswith('# '):
                story.append(Paragraph(f'<b>{line[2:]}</b>', styles['Title']))
            elif line.startswith('## '):
                story.append(Paragraph(f'<b>{line[3:]}</b>', styles['Heading1']))
            elif line.startswith('### '):
                story.append(Paragraph(f'<b>{line[4:]}</b>', styles['Heading2']))
            elif line.startswith('|'):
                # 表格行,简化处理
                story.append(Paragraph(line, styles['Code']))
            else:
                # 去除 markdown 符号
                clean = line.replace('**', '').replace('*', '').replace('`', '').replace('【', '[').replace('】', ']')
                story.append(Paragraph(clean, styles['Normal']))

        doc.build(story)
        return True
    except Exception as e:
        print(f'    Python 转 PDF 失败:{e}')
        return False

def main():
    print('=' * 80)
    print('7 份备案材料 .md → .pdf 转换工具')
    print('=' * 80)

    # 创建输出目录
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f'\n输出目录:{OUT_DIR}')

    # 查 3 方案
    print('\n=== 查 3 种转换方案 ===')
    a_ok, a_msg = method_a_pandoc()
    b_ok, b_msg = method_b_python()
    c_ok, c_msg = method_c_manual()
    print(f'方案 A (pandoc + wkhtmltopdf):{"可用" if a_ok else "不可用"} - {a_msg}')
    print(f'方案 B (Python reportlab):{"可用" if b_ok else "不可用"} - {b_msg}')
    print(f'方案 C (VS Code 插件):可用 - {c_msg}')

    # 自动选方案
    if a_ok:
        method = 'A'
        method_name = 'pandoc + wkhtmltopdf'
    elif b_ok:
        method = 'B'
        method_name = 'Python reportlab'
    else:
        method = 'C'
        method_name = 'VS Code 插件(手动)'

    print(f'\n自动选择:方案 {method}({method_name})')

    # 转换 4 份算法备案材料
    print('\n=== 转换 4 份算法备案材料 ===')
    converted = 0
    for f in ALGO_FILES:
        src = os.path.join(BASE, f)
        dst = os.path.join(OUT_DIR, f.replace('.md', '.pdf'))

        if not os.path.exists(src):
            print(f'  [跳过] {f} 不存在')
            continue

        print(f'  转换:{f}')

        success = False
        if method == 'A':
            success = convert_with_pandoc(src, dst)
        elif method == 'B':
            success = convert_with_python(src, dst)

        if success and os.path.exists(dst):
            size = os.path.getsize(dst)
            print(f'    ✅ {os.path.basename(dst)} ({size} 字节)')
            converted += 1
        else:
            print(f'    ❌ 转换失败')
            print(f'    [用方案 C 手动] 在 VS Code 打开 {f} → 右键 → Markdown PDF: Export (pdf)')

    # 检查 3 份 User PDF
    print('\n=== 检查 3 份 User 必拍 PDF ===')
    user_count = 0
    for f in USER_PDFS:
        dst = os.path.join(OUT_DIR, f)
        if os.path.exists(dst):
            size = os.path.getsize(dst)
            print(f'  ✅ {f} ({size} 字节)')
            user_count += 1
        else:
            print(f'  ❌ {f} 缺失 - User 必拍:')
            print(f'     1. 用"全能扫描王"APP 拍')
            print(f'     2. 存到 {dst}')
            print(f'     3. 命名:{f}')

    # 总计
    print(f'\n=== 完成 ===')
    print(f'算法备案 4 份:已转换 {converted}/4')
    print(f'User 必拍 3 份:已有 {user_count}/3')
    print(f'总计:{converted + user_count}/7')

    if converted == 4 and user_count == 3:
        print('\n✅ 7 份 PDF 全部就绪,可以上传工信部 / 网信办')
    else:
        print(f'\n⚠️ 缺 {7 - converted - user_count} 份,需补')

if __name__ == '__main__':
    main()
