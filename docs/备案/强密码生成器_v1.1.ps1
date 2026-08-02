# Strong password generator v1.1 (English comments + UTF-8 BOM)
# Author: Mavis
# Date: 2026-07-01 13:18

param(
    [int]$Length = 20,
    [int]$Count = 5,
    [switch]$IncludeSpecial,
    [switch]$NoAmbiguous
)

$UpperCase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
$LowerCase = 'abcdefghijklmnopqrstuvwxyz'
$Numbers = '0123456789'
$SpecialChars = '!@#$%^&*()_+-=[]{}|;:,.<>?'

if ($NoAmbiguous) {
    $UpperCase = $UpperCase -replace '[IO]', ''
    $LowerCase = $LowerCase -replace '[lo]', ''
    $Numbers = $Numbers -replace '[01]', ''
    $SpecialChars = $SpecialChars -replace '[<>,;:]', ''
}

if (-not $PSBoundParameters.ContainsKey('IncludeSpecial')) {
    $IncludeSpecial = $true
}

$AllChars = $UpperCase + $LowerCase + $Numbers
if ($IncludeSpecial) {
    $AllChars += $SpecialChars
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Mavis strong password generator v1.1" -ForegroundColor Cyan
Write-Host "  Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "  Length: $Length / Count: $Count / Special: $IncludeSpecial / NoAmbiguous: $NoAmbiguous" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$Passwords = @()

for ($i = 1; $i -le $Count; $i++) {
    $Password = ""

    $Password += $UpperCase[(Get-Random -Maximum $UpperCase.Length)]
    $Password += $LowerCase[(Get-Random -Maximum $LowerCase.Length)]
    $Password += $Numbers[(Get-Random -Maximum $Numbers.Length)]
    if ($IncludeSpecial) {
        $Password += $SpecialChars[(Get-Random -Maximum $SpecialChars.Length)]
    }

    while ($Password.Length -lt $Length) {
        $Password += $AllChars[(Get-Random -Maximum $AllChars.Length)]
    }

    $Shuffled = -join ($Password.ToCharArray() | Get-Random -Count $Password.Length)

    $Passwords += $Shuffled
    Write-Host "[$i] $Shuffled" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Character class verification:" -ForegroundColor Cyan
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

    $Status = if ($Valid) { "[PASS]" } else { "[FAIL]" }
    $Color = if ($Valid) { "Green" } else { "Red" }

    Write-Host "  [$($i+1)] Upper:$HasUpper Lower:$HasLower Number:$HasNumber Special:$HasSpecial $Status" -ForegroundColor $Color
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Strength score (each password):" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

for ($i = 0; $i -lt $Passwords.Count; $i++) {
    $Pwd = $Passwords[$i]
    $Score = 0

    if ($Pwd.Length -ge 8) { $Score += 1 }
    if ($Pwd.Length -ge 12) { $Score += 1 }
    if ($Pwd.Length -ge 16) { $Score += 1 }
    if ($Pwd.Length -ge 20) { $Score += 1 }

    if ($Pwd -cmatch '[A-Z]') { $Score += 1 }
    if ($Pwd -cmatch '[a-z]') { $Score += 1 }
    if ($Pwd -cmatch '[0-9]') { $Score += 1 }
    if ($Pwd -match '[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]') { $Score += 1 }

    $UniqueChars = ($Pwd.ToCharArray() | Select-Object -Unique).Count
    if ($UniqueChars -ge 8) { $Score += 1 }
    if ($UniqueChars -ge 12) { $Score += 1 }

    $Rating = switch ($Score) {
        { $_ -ge 10 } { "5/5 extremely strong (centuries to crack)" }
        { $_ -ge 8 } { "4/5 very strong (years to crack)" }
        { $_ -ge 6 } { "3/5 medium (months to crack)" }
        { $_ -ge 4 } { "2/5 weak (weeks to crack)" }
        default { "1/5 very weak (hours-days to crack)" }
    }

    Write-Host "  [$($i+1)] Score: $Score / 11 - $Rating" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Usage:" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  1. Pick 1 password and copy" -ForegroundColor White
Write-Host "  2. Paste when changing aliyun password" -ForegroundColor White
Write-Host "  3. DO NOT save to local plaintext file" -ForegroundColor White
Write-Host "  4. Use password manager (1Password / Bitwarden / KeePass)" -ForegroundColor White
Write-Host ""
Write-Host "  Aliyun password change path: Avatar -> Account Mgmt -> Security -> Login Password -> Modify" -ForegroundColor White
Write-Host ""