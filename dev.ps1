# dev.ps1 - 启动 zhishe-a2a 开发环境
# 用法: .\dev.ps1
# 作用: 把 Python 3.11 加进当前会话 PATH(每次新 shell 都要跑一次)

$ErrorActionPreference = 'Stop'

# 1) 把 Python 3.11 加到 PATH 前缀
$pyHome = "$env:LOCALAPPDATA\Programs\Python\Python311"
if (-not (Test-Path "$pyHome\python.exe")) {
    Write-Error "Python 3.11 not found at $pyHome. Please install it first."
}
$env:Path = "$pyHome;$pyHome\Scripts;$env:Path"

# 2) 切到项目根
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# 3) 验证
Write-Host "=== zhishe-a2a dev shell ===" -ForegroundColor Cyan
Write-Host "python: $(python --version)"
Write-Host "pip:    $(pip --version)"
Write-Host "cwd:    $(Get-Location)"

# 4) 如果 .venv 不存在,创建一个
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "`n>>> Creating venv..." -ForegroundColor Yellow
    python -m venv .venv
}

# 5) 激活 venv(用 .\.venv\Scripts\Activate.ps1)
Write-Host "`n>>> Activating venv..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1
Write-Host "venv:   $(python --version) at $(python -c 'import sys; print(sys.executable)')"

# 6) 显示下一步
Write-Host "`nNext steps:" -ForegroundColor Green
Write-Host "  pip install -r requirements.txt     # install deps"
Write-Host "  uvicorn app.main:app --reload --port 8765"
Write-Host "  curl http://localhost:8765/.well-known/agent-card`n"
