Add-Type -AssemblyName System.Drawing
$src = 'E:\小红书\学习AI大模型如何应用\千问AI Agent\微信图片_2026-05-18_231603_306.png'
$dst = 'D:\知设Agent生态\千问AI Agent\zhishe-a2a\docs\zhishe_avatar.png'

# 读原图
$img = [System.Drawing.Image]::FromFile($src)
Write-Host "原图: $($img.Width)x$($img.Height)"

# 算 1:1 居中裁剪 + 缩放到 256x256
$side = [Math]::Min($img.Width, $img.Height)
$x = ($img.Width - $side) / 2
$y = ($img.Height - $side) / 2

$bmp = New-Object System.Drawing.Bitmap 256, 256
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = 'HighQualityBicubic'
$g.SmoothingMode = 'HighQuality'
$g.PixelOffsetMode = 'HighQuality'
$g.DrawImage($img, 0, 0, 256, 256)

$bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
$img.Dispose()

$dstInfo = Get-Item $dst
Write-Host "输出: $dst"
Write-Host "大小: $($dstInfo.Length) 字节"
