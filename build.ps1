# Baut das portable Paket nach dist\supersubber\ (PyInstaller onedir). Voraussetzung: .venv mit requirements + bin\ (fetch-bins.ps1).
Set-Location $PSScriptRoot
# PyInstaller loggt auf stderr -> in PS 5.1 kein ErrorActionPreference=Stop, sondern Exit-Code prüfen
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name supersubber `
    --icon "assets\icon.ico" `
    --add-data "bin;bin" `
    --add-data "assets;assets" `
    --add-data "THIRD-PARTY.md;." `
    --collect-all subliminal --copy-metadata subliminal `
    --collect-all guessit --collect-all babelfish --copy-metadata babelfish `
    --collect-all tkinterdnd2 `
    --hidden-import dogpile.cache.backends.memory `
    run.py 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match 'ERROR|WARNING: Hidden import|not found|Traceback' }
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller fehlgeschlagen (Exit $LASTEXITCODE)"; exit 1 }
# PyInstaller 6 stuft die ffmpeg-DLLs aus bin\ als Binaries ein und legt ihre Abhaengigkeiten zusaetzlich nach
# _internal\ - das verdoppelt ~65 MB. Nur ffmpeg.exe in bin\ braucht sie, Python nie: Duplikate entfernen.
Get-ChildItem "dist\supersubber\_internal\bin\*.dll" | ForEach-Object {
    $dup = Join-Path "dist\supersubber\_internal" $_.Name
    if (Test-Path $dup) { Remove-Item $dup }
}
$ver =(Get-Content supersubber\__init__.py | Select-String '__version__ = "(.*)"').Matches[0].Groups[1].Value
$zip = "dist\supersubber-$ver-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\supersubber" -DestinationPath $zip
Write-Host "Fertig: $zip  ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)"
