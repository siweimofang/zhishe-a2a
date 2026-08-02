# 强密码生成器 PowerShell 脚本
# 作者:Mavis
# 时间:2026-07-01 07:59
# 用途:User 改主账号密码时使用 / 关键操作保护密码 / 各种账号改密

param(
    [int]$Length = 20,          # 密码长度(Mavis 强推 20+ 字符)
    [int]$Count = 5,             # 生成多少个候选
    [switch]$IncludeSpecial,    # 包含特殊符号
    [switch]$NoAmbiguous        # 排除易混淆字符(0/O/1/l/I)
)

# 字符集
$UpperCase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
$LowerCase = 'abcdefghijklmnopqrstuvwxyz'
$Numbers = '0123456789'
$SpecialChars = '!@#$%^&*()_+-=[]{}|;:,.<>?'

if ($NoAmbiguous) {
    # 排除易混淆字符
    $UpperCase = $UpperCase -replace '[IO]', ''
    $LowerCase = $LowerCase -replace '[lo]', ''
    $Numbers = $Numbers -replace '[01]', ''
    $SpecialChars = $SpecialChars -replace '[<>,;:]', ''
}

# 默认包含特殊符号
if (-not $PSBoundParameters.ContainsKey('IncludeSpecial')) {
    $IncludeSpecial = $true
}

# 必含 4 类字符
$AllChars = $UpperCase + $LowerCase + $Numbers
if ($IncludeSpecial) {
    $AllChars += $SpecialChars
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Mavis 强密码生成器 v1.0" -ForegroundColor Cyan
Write-Host "  生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "  长度: $Length / 数量: $Count / 特殊符号: $IncludeSpecial / 排除易混淆: $NoAmbiguous" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$Passwords = @()

for ($i = 1; $i -le $Count; $i++) {
    $Password = ""

    # 必含:至少 1 个大写 / 1 个小写 / 1 个数字 / 1 个特殊字符
    $Password += $UpperCase[(Get-Random -Maximum $UpperCase.Length)]
    $Password += $LowerCase[(Get-Random -Maximum $LowerCase.Length)]
    $Password += $Numbers[(Get-Random -Maximum $Numbers.Length)]
    if ($IncludeSpecial) {
        $Password += $SpecialChars[(Get-Random -Maximum $SpecialChars.Length)]
    }

    # 补足到指定长度
    while ($Password.Length -lt $Length) {
        $Password += $AllChars[(Get-Random -Maximum $AllChars.Length)]
    }

    # 打乱顺序(避免前几位都是固定字符)
    $Shuffled = -join ($Password.ToCharArray() | Get-Random -Count $Password.Length)

    $Passwords += $Shuffled
    Write-Host "[$i] $Shuffled" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  4 类字符必含验证:" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Passwords.Count; $i++) {
    $Pwd = $Passwords[$i]
    $HasUpper = $Pwd -cmatch '[A-Z]'
    $HasLower = $Pwd -cmatch '[a-z]'
    $HasNumber = $Pwd -cmatch '[0-9]'
    $HasSpecial = $Pwd -match '[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]'

    $Valid = $HasUpper -and $HasLower -and $HasNumber
    if ($IncludeSpecial) {
        $Valid = $Valid -and $HasSpecial
    }

    $Status = if ($Valid) { "✅ 通过" } else { "❌ 不通过" }
    $Color = if ($Valid) { "Green" } else { "Red" }

    Write-Host "  [$($i+1)] 大写:$HasUpper 小写:$HasLower 数字:$HasNumber 特殊:$HasSpecial $Status" -ForegroundColor $Color
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  强密码强度评分(每个密码):" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Passwords.Count; $i++) {
    $Pwd = $Passwords[$i]
    $Score = 0

    # 长度评分
    if ($Pwd.Length -ge 8) { $Score += 1 }
    if ($Pwd.Length -ge 12) { $Score += 1 }
    if ($Pwd.Length -ge 16) { $Score += 1 }
    if ($Pwd.Length -ge 20) { $Score += 1 }

    # 复杂度评分
    if ($Pwd -cmatch '[A-Z]') { $Score += 1 }
    if ($Pwd -cmatch '[a-z]') { $Score += 1 }
    if ($Pwd -cmatch '[0-9]') { $Score += 1 }
    if ($Pwd -match '[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]') { $Score += 1 }

    # 多样性评分
    $UniqueChars = ($Pwd.ToCharArray() | Select-Object -Unique).Count
    if ($UniqueChars -ge 8) { $Score += 1 }
    if ($UniqueChars -ge 12) { $Score += 1 }

    $Rating = switch ($Score) {
        { $_ -ge 10 } { "⭐⭐⭐⭐⭐ 极强(预计破解时间:几百年+)" }
        { $_ -ge 8 } { "⭐⭐⭐⭐ 很强(预计破解时间:几年)" }
        { $_ -ge 6 } { "⭐⭐⭐ 中等(预计破解时间:几月)" }
        { $_ -ge 4 } { "⭐⭐ 较弱(预计破解时间:几周)" }
        default { "⭐ 弱(预计破解时间:几小时-几天)" }
    }

    Write-Host "  [$($i+1)] 评分:$Score / 11 - $Rating" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  使用方法:" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  1. 选 1 个密码复制" -ForegroundColor White
Write-Host "  2. 改阿里云密码时粘贴" -ForegroundColor White
Write-Host "  3. **不要保存到本地明文文件**" -ForegroundColor White
Write-Host "  4. 推荐存密码管理器(1Password / Bitwarden / KeePass)" -ForegroundColor White
Write-Host ""
Write-Host "  阿里云主账号改密路径:头像 → 账号管理 → 安全设置 → 登录密码 → 修改" -ForegroundColor White
Write-Host ""

# 可选:复制到剪贴板(注释掉,Mavis 不擅自写剪贴板)
# $Passwords[0] | Set-Clipboard
# Write-Host "  第一个密码已复制到剪贴板" -ForegroundColor Magenta