# Aktualisiert das Scoop-Manifest im Bucket-Repo (..\scoop-bucket) auf die aktuelle Version und pusht es.
# Aufruf nach dem GitHub-Release, wenn das Zip als Release-Asset online ist:  .\scoop-release.ps1
# Voraussetzung: ..\scoop-bucket ist ein Klon von github.com/Cosmopolyte/scoop-bucket mit Push-Recht.
Set-Location $PSScriptRoot
$ver = (Get-Content supersubber\__init__.py | Select-String '__version__ = "(.*)"').Matches[0].Groups[1].Value
$zip = "dist\supersubber-$ver-win64.zip"
if (-not (Test-Path $zip)) { Write-Host "Zip fehlt: $zip"; exit 1 }
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
$bucket = Join-Path $PSScriptRoot "..\scoop-bucket"
if (-not (Test-Path (Join-Path $bucket ".git"))) { Write-Host "Bucket-Repo fehlt: $bucket"; exit 1 }
New-Item -ItemType Directory -Force (Join-Path $bucket "bucket") | Out-Null
$manifest = [ordered]@{
    version     = $ver
    description = "Find & Sync Subtitles - downloads missing subtitles for whole folders and syncs them against the audio track"
    homepage    = "https://github.com/Cosmopolyte/supersubber"
    license     = "MIT"
    url         = "https://github.com/Cosmopolyte/supersubber/releases/download/v$ver/supersubber-$ver-win64.zip"
    hash        = $hash
    extract_dir = "supersubber"
    bin         = "supersubber.exe"
    shortcuts   = @(, @("supersubber.exe", "SuperSubber"))
    persist     = @()
    checkver    = "github"
    autoupdate  = [ordered]@{ url = 'https://github.com/Cosmopolyte/supersubber/releases/download/v$version/supersubber-$version-win64.zip' }
}
$json = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $bucket "bucket\supersubber.json"), $json + "`n", (New-Object Text.UTF8Encoding $false))
Set-Location $bucket
git add bucket\supersubber.json
git commit -q -m "supersubber $ver" 2>$null
git push -q origin HEAD:main
Write-Host "Scoop-Manifest $ver gepusht (sha256 $($hash.Substring(0,12))...)"
