# Reproduce the existing green あ brand mark; no downloaded art or dependencies.
# Run from the repository root in Windows PowerShell with Yu Gothic installed.
Add-Type -AssemblyName System.Drawing
$outputDirectory = Join-Path $PSScriptRoot '../frontend/pwa'
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
foreach ($spec in @(@('icon-192.png',192),@('icon-512.png',512),@('icon-maskable-512.png',512),@('apple-touch-icon.png',180),@('favicon-32.png',32))) {
    $size = [int]$spec[1]; $scale = 4; $edge = $size * $scale
    $bitmap = New-Object System.Drawing.Bitmap($edge,$edge)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = 'AntiAlias'; $graphics.TextRenderingHint = 'AntiAliasGridFit'
    $green = [System.Drawing.ColorTranslator]::FromHtml('#285d4e')
    $cream = [System.Drawing.ColorTranslator]::FromHtml('#f5f6f1')
    $graphics.Clear($cream)
    $brush = New-Object System.Drawing.SolidBrush($green)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    if ($spec[0] -like '*maskable*') { $graphics.Clear($green) }
    else {
        $margin = $edge * .07; $radius = $edge * .18; $length = $edge - 2*$margin
        $path.AddArc($margin,$margin,$radius,$radius,180,90)
        $path.AddArc($margin+$length-$radius,$margin,$radius,$radius,270,90)
        $path.AddArc($margin+$length-$radius,$margin+$length-$radius,$radius,$radius,0,90)
        $path.AddArc($margin,$margin+$length-$radius,$radius,$radius,90,90)
        $path.CloseFigure(); $graphics.FillPath($brush,$path)
    }
    $font = New-Object System.Drawing.Font('Yu Gothic',($edge*.55),[System.Drawing.FontStyle]::Bold,[System.Drawing.GraphicsUnit]::Pixel)
    $format = New-Object System.Drawing.StringFormat
    $format.Alignment = 'Center'; $format.LineAlignment = 'Center'
    $graphics.DrawString([string][char]0x3042,$font,[System.Drawing.Brushes]::White,[System.Drawing.RectangleF]::new(0,($edge*.14),$edge,$edge),$format)
    $small = New-Object System.Drawing.Bitmap($size,$size)
    $resize = [System.Drawing.Graphics]::FromImage($small)
    $resize.InterpolationMode = 'HighQualityBicubic'; $resize.DrawImage($bitmap,0,0,$size,$size)
    $small.Save((Join-Path $outputDirectory $spec[0]),[System.Drawing.Imaging.ImageFormat]::Png)
    $resize.Dispose();$small.Dispose();$format.Dispose();$font.Dispose();$path.Dispose();$brush.Dispose();$graphics.Dispose();$bitmap.Dispose()
}
# PNG-backed ICO for browsers requesting the conventional /favicon.ico URL.
$png = [System.IO.File]::ReadAllBytes((Join-Path $outputDirectory 'favicon-32.png'))
$stream = [System.IO.File]::Create((Join-Path $outputDirectory 'favicon.ico'))
$writer = New-Object System.IO.BinaryWriter($stream)
$writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]1)
$writer.Write([byte]32);$writer.Write([byte]32);$writer.Write([byte]0);$writer.Write([byte]0)
$writer.Write([uint16]1);$writer.Write([uint16]32);$writer.Write([uint32]$png.Length);$writer.Write([uint32]22);$writer.Write($png)
$writer.Dispose();$stream.Dispose()
