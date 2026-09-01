# subsync.ps1 — Find & Sync Subtitles
# Lädt fehlende Untertitel via subliminal und synct sie mit alass gegen die Tonspur.
# Aufruf: subsync.ps1 <Ordner> [-Languages ru,de,en]   (rekursiv; auch via Explorer-Kontextmenü)
# Provider-Zugangsdaten (OpenSubtitles): %LOCALAPPDATA%\subliminal\subliminal\subliminal.toml
# Doku: Obsidian "Subtitles mit Video synchronisieren.md"

param(
    [Parameter(Mandatory = $true)][string]$Folder,
    [string]$Languages = 'ru'
)

# ---- Konfiguration -----------------------------------------------------------
$AlassDir   = 'C:\Tools\alass'
$Subliminal = "$env:USERPROFILE\.local\bin\subliminal.exe"
$VideoExt   = '.mkv', '.mp4', '.avi', '.m4v'
$MinSizeMB  = 50                          # kleinere Dateien = Samples, ignorieren
# -----------------------------------------------------------------------------

$Langs = @($Languages -split '[,; ]+' | Where-Object { $_ })
$env:ALASS_FFMPEG_PATH  = "$AlassDir\ffmpeg\bin\ffmpeg.exe"
$env:ALASS_FFPROBE_PATH = "$AlassDir\ffmpeg\bin\ffprobe.exe"
$Alass = "$AlassDir\bin\alass-cli.exe"

if (-not (Test-Path -LiteralPath $Folder -PathType Container)) {
    Write-Host "Ordner nicht gefunden: $Folder" -ForegroundColor Red
    Read-Host 'Enter zum Schliessen'; exit 1
}

$videos = Get-ChildItem -LiteralPath $Folder -Recurse -File |
    Where-Object { $VideoExt -contains $_.Extension.ToLower() -and $_.Length -gt $MinSizeMB * 1MB }

if (-not $videos) {
    Write-Host "Keine Videodateien in $Folder gefunden." -ForegroundColor Yellow
    Read-Host 'Enter zum Schliessen'; exit 0
}

Write-Host "=== Find & Sync Subtitles ===" -ForegroundColor Cyan
Write-Host "Ordner : $Folder"
Write-Host "Videos : $($videos.Count)   Sprachen: $($Langs -join ', ')"
Write-Host ''

$synced  = @()   # neu geladen + gesynct
$raw     = @()   # geladen, aber alass gescheitert -> unsynct uebernommen
$missing = @()   # kein Sub gefunden

# Videos, denen mindestens eine Sprache fehlt
$todo = @($videos | Where-Object {
    $v = $_
    ($Langs | Where-Object {
        -not (Test-Path -LiteralPath "$($v.DirectoryName)\$($v.BaseName).$_.srt") -and
        -not (Test-Path -LiteralPath "$($v.DirectoryName)\$($v.BaseName).$_.ass")
    }).Count -gt 0
})
$done = @($videos | Where-Object { $todo -notcontains $_ })

if (-not $todo) {
    Write-Host "Alle Videos haben bereits Untertitel in: $($Langs -join ', ')" -ForegroundColor Green
    Read-Host 'Enter zum Schliessen'; exit 0
}

$tmp = Join-Path $env:TEMP ("subsync-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $tmp | Out-Null

Write-Host "[1/2] Lade Untertitel (subliminal) fuer $($todo.Count) Video(s)..." -ForegroundColor Cyan
$langArgs = @(); foreach ($l in $Langs) { $langArgs += '-l'; $langArgs += $l }
& $Subliminal download @langArgs -d $tmp @($todo.FullName)
Write-Host ''

Write-Host "[2/2] Synce gegen Tonspur (alass)..." -ForegroundColor Cyan
foreach ($v in $todo) {
    foreach ($lang in $Langs) {
        $target = "$($v.DirectoryName)\$($v.BaseName).$lang.srt"
        if ((Test-Path -LiteralPath $target) -or
            (Test-Path -LiteralPath "$($v.DirectoryName)\$($v.BaseName).$lang.ass")) { continue }

        $dl = Get-ChildItem -LiteralPath $tmp -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq "$($v.BaseName).$lang.srt" } | Select-Object -First 1
        if (-not $dl) { $missing += "$($v.Name)  [$lang]"; continue }

        Write-Host "  $($v.Name)  [$lang]" -ForegroundColor Gray
        & $Alass $v.FullName $dl.FullName $target 2>&1 |
            Where-Object { $_ -match 'shifted|framerate ratio|error|warn' } |
            ForEach-Object { Write-Host "    $_" }

        if ((Test-Path -LiteralPath $target) -and $LASTEXITCODE -eq 0) {
            $synced += "$($v.Name)  [$lang]"
        } else {
            Copy-Item -LiteralPath $dl.FullName -Destination $target -Force
            $raw += "$($v.Name)  [$lang]"
        }
    }
}
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

Write-Host ''
Write-Host '=== Ergebnis ===' -ForegroundColor Cyan
Write-Host ("  Neu geladen + gesynct : {0}" -f $synced.Count) -ForegroundColor Green
Write-Host ("  Schon vorhanden       : {0}" -f $done.Count)
if ($raw.Count) {
    Write-Host ("  Nur geladen (Sync fehlgeschlagen, unsynct uebernommen): {0}" -f $raw.Count) -ForegroundColor Yellow
    $raw | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}
if ($missing.Count) {
    Write-Host ("  Kein Untertitel gefunden: {0}" -f $missing.Count) -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Write-Host '  -> Datei unklar benannt? Serienname + SxxExx noetig fuer die Erkennung.' -ForegroundColor Red
    Write-Host '     Alternativ Sub manuell besorgen und mit alass direkt syncen (siehe Obsidian-Notiz).' -ForegroundColor Red
}
Write-Host ''
Read-Host 'Enter zum Schliessen'
