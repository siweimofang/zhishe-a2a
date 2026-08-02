$src = 'C:\Users\Administrator\.mavis\sessions\mvs_489cb3b415ef42ae9f33a5cfaa430da9\workspace\matrix-media-1781565056259-4101f1ff.png'
if (Test-Path $src) {
    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.NameSpace(0xA)  # Recycle Bin
    $item = $shell.NameSpace((Split-Path $src)).ParseName((Split-Path $src -Leaf))
    if ($item -ne $null) {
        $item.InvokeVerb('delete')
        Write-Host "已移到回收站: $src"
    } else {
        Write-Host "无法移动,改用 Remove-Item"
        Remove-Item $src -Force
        Write-Host "已删除: $src"
    }
} else {
    Write-Host "文件不存在: $src"
}
