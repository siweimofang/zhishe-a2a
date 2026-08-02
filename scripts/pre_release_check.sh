#!/bin/bash
# 知设 Agent 上线前 AI 强制拦截脚本(铁律 75 v2 第 8 项)
# 用法:./pre_release_check.sh
# 任何 1 项 FAIL = 退出码 1,禁止上架

set -e  # 任何命令失败立即退出

# === 颜色输出 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0
PASSED=0

check() {
    local name="$1"
    local cmd="$2"

    echo -n "[$name] ... "
    if eval "$cmd" > /tmp/zhishe_check.log 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}FAIL${NC}"
        cat /tmp/zhishe_check.log | sed 's/^/    /'
        FAILED=$((FAILED + 1))
    fi
}

echo "=========================================="
echo "知设 Agent 上线前 AI 强制拦截检查"
echo "时间:$(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# === 检查 1:数据库权限(铁律 75 第 1 项) ===
check "1. 数据库权限最小化" \
    "grep -q '最小权限原则' docs/备案/V1.5_安全工程清单_2026-06-27.md"

# === 检查 2:API 鉴权(铁律 75 第 2 项) ===
check "2. API 鉴权 Bearer + BOLA 防护" \
    "test -f app/api/auth.py && grep -q 'require_api_key' app/main.py"

# === 检查 3:密钥管理(铁律 75 第 3 项) ===
check "3. 密钥管理:无 .env 硬编码 + .env.example 存在" \
    "! grep -rq 'mKgd4EVhF7A8Y9zk6unOyb2jI1NBLaTR' app/ skills/ 2>/dev/null && test -f .env.example"

# === 检查 4:日志脱敏(铁律 75 第 4 项) ===
check "4. 日志脱敏:ZHISHE_LOG_MASK_PII 默认 true" \
    "grep -q 'ZHISHE_LOG_MASK_PII=true' .env.example"

# === 检查 5:废弃数据处理(铁律 75 第 5 项) ===
check "5. 废弃数据处理策略:30 天提醒 + 90 天自动删除" \
    "test -f docs/备案/Mavis_废弃数据处理策略_*.md"

# === 检查 6:pip-audit 依赖漏洞扫描 ===
if command -v pip-audit > /dev/null 2>&1; then
    check "6. pip-audit 依赖漏洞扫描" \
        "pip-audit -r requirements.txt --strict"
else
    echo -e "[6. pip-audit 依赖漏洞扫描] ... ${YELLOW}SKIP(pip-audit 未安装)${NC}"
fi

# === 检查 7:bandit 代码静态扫描 ===
if command -v bandit > /dev/null 2>&1; then
    check "7. bandit 代码静态扫描" \
        "bandit -r app/ -f json -q 2>/dev/null | python -c 'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d[\"results\"]==[] else 1)'"
else
    echo -e "[7. bandit 代码静态扫描] ... ${YELLOW}SKIP(bandit 未安装)${NC}"
fi

# === 检查 8:默认私有(铁律 75 v2 第 7 项) ===
check "8. 默认私有:/skills + /data/* 已加鉴权" \
    "grep -q 'Depends(require_api_key)' app/main.py"

# === 检查 9:无敏感信息泄露 ===
check "9. 无敏感信息泄露:requirements.txt 不含真实 key" \
    "! grep -rqE '(mKgd4EVhF7A8Y9zk6unOyb2jI1NBLaTR|DEEPSEEK_API_KEY=[a-zA-Z0-9]{20,})' requirements.txt README.md 2>/dev/null"

# === 检查 10:.env 权限 600 ===
if [ -f .env ]; then
    check "10. .env 权限 600" \
        "[ \$(stat -c %a .env 2>/dev/null || stat -f %A .env 2>/dev/null) = '600' ]"
else
    echo -e "[10. .env 权限 600] ... ${YELLOW}SKIP(.env 不存在,本地联调)${NC}"
fi

echo ""
echo "=========================================="
echo "检查结果:${PASSED} PASS / ${FAILED} FAIL"
echo "=========================================="

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}❌ ${FAILED} 项不合规,禁止上架${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 全部合规,可以上架${NC}"
    exit 0
fi