# 知设 Agent pre-commit 拦截脚本(Windows PowerShell 版)
# 铁律 75 v2 第 8 项:上线前 AI 强制拦截
# 用法:在 .git/hooks/pre-commit 加一行:
#   powershell -ExecutionPolicy Bypass -File scripts/pre_commit_security_check.ps1

$ErrorActionPreference = "Stop"

# === 颜色 ===
function Write-Pass { param($msg) Write-Host "[$msg] ... PASS" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "[$msg] ... FAIL" -ForegroundColor Red }
function Write-Skip { param($msg) Write-Host "[$msg] ... SKIP" -ForegroundColor Yellow }

$failed = 0
$passed = 0

# === 检查 1:无 API Key 硬编码 ===
$msg = "1. 无 API Key 硬编码"
try {
    $hits = Select-String -Path "app\*.py", "skills\**\*.py" -Pattern "mKgd4EVhF7A8Y9zk6unOyb2jI1NBLaTR" -ErrorAction SilentlyContinue
    if ($hits) {
        Write-Fail $msg
        $hits | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line)" }
        $failed++
    } else {
        Write-Pass $msg
        $passed++
    }
} catch {
    Write-Skip "$msg ($($_.Exception.Message))"
}

# === 检查 2:无 DeepSeek 真实 key ===
$msg = "2. 无 DeepSeek 真实 key"
try {
    $hits = Select-String -Path "app\*.py", "skills\**\*.py", ".env.example" -Pattern "DEEPSEEK_API_KEY=[a-zA-Z0-9]{20,}" -ErrorAction SilentlyContinue
    if ($hits) {
        Write-Fail $msg
        $hits | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line)" }
        $failed++
    } else {
        Write-Pass $msg
        $passed++
    }
} catch {
    Write-Skip "$msg ($($_.Exception.Message))"
}

# === 检查 3:无数据库连接串含密码 ===
$msg = "3. 无数据库连接串含密码"
try {
    $hits = Select-String -Path "app\*.py", "skills\**\*.py" -Pattern "(postgresql|mysql)://[^:]+:[^@]+@" -ErrorAction SilentlyContinue
    if ($hits) {
        Write-Fail $msg
        $hits | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line)" }
        $failed++
    } else {
        Write-Pass $msg
        $passed++
    }
} catch {
    Write-Skip "$msg ($($_.Exception.Message))"
}

# === 检查 4:requirements.txt 已更新 ===
$msg = "4. requirements.txt 文件存在"
if (Test-Path "requirements.txt") {
    Write-Pass $msg
    $passed++
} else {
    Write-Fail $msg
    $failed++
}

# === 检查 5:无 .env 文件被 git 追踪 ===
$msg = "5. .env 未被 git 追踪"
try {
    $tracked = git ls-files .env 2>$null
    if ($tracked) {
        Write-Fail $msg
        Write-Host "    .env 被 git 追踪(违反铁律 75 第 3 项)"
        $failed++
    } else {
        Write-Pass $msg
        $passed++
    }
} catch {
    Write-Skip "$msg (git 未初始化)"
}

Write-Host ""
Write-Host "=========================================="
Write-Host "检查结果: $passed PASS / $failed FAIL"
Write-Host "=========================================="

if ($failed -gt 0) {
    Write-Host "❌ $failed 项不合规,git commit 已拦截" -ForegroundColor Red
    exit 1
} else {
    Write-Host "✅ 全部合规,git commit 通过" -ForegroundColor Green
    exit 0
}