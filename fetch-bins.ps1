# Lädt alass (inkl. gebündeltem ffmpeg) und legt die Binaries nach bin\ — Voraussetzung für Entwicklung und Build.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$zip = Join-Path $env:TEMP "alass-windows64.zip"
$tmp = Join-Path $env:TEMP "alass-windows64"
Invoke-WebRequest -Uri "https://github.com/kaegi/alass/releases/download/v2.0.0/alass-windows64.zip" -OutFile $zip
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp
New-Item -ItemType Directory -Force "$root\bin" | Out-Null
Copy-Item "$tmp\alass-windows64\bin\alass-cli.exe" "$root\bin\"
Copy-Item "$tmp\alass-windows64\ffmpeg\bin\*" "$root\bin\"
Copy-Item "$tmp\alass-windows64\bin\LICENSE.txt" "$root\bin\LICENSE-alass.txt"
Copy-Item "$tmp\alass-windows64\ffmpeg\LICENSE.txt" "$root\bin\LICENSE-ffmpeg.txt"
Remove-Item -Recurse -Force $tmp, $zip
Write-Host "bin\ befüllt:"; Get-ChildItem "$root\bin" | Select-Object -ExpandProperty Name
