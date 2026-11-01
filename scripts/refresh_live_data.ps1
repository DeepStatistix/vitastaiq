<#
Refreshes the Mandi dashboard data (site/demo/mandi/live.js) and publishes it to GitHub.

It is meant to run daily from Windows Task Scheduler, inside a DEDICATED CLONE of the repository,
so it never touches your working copy. It only ever commits that one file.

  powershell -File refresh_live_data.ps1 -RepoDir <clone> -PythonExe <python.exe> -EnvFile <.env> [-DryRun]

  -RepoDir    a clone of the repo used only for this automation
  -PythonExe  any Python 3 (fetch_live.py uses only the standard library)
  -EnvFile    a .env file containing DATA_GOV_API_KEY (the key is read, never copied or logged)
  -DryRun     fetch to a temporary file and report, without any git changes or pushes

Log: %LOCALAPPDATA%\VitastaIQ\refresh.log
#>
param(
  [Parameter(Mandatory = $true)] [string]$RepoDir,
  [Parameter(Mandatory = $true)] [string]$PythonExe,
  [Parameter(Mandatory = $true)] [string]$EnvFile,
  [switch]$DryRun
)

$logDir = Join-Path $env:LOCALAPPDATA "VitastaIQ"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "refresh.log"
function Log([string]$m) { $l = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $m; Add-Content -Path $log -Value $l; Write-Host $l }
function Git { & git @args; if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed (exit $LASTEXITCODE)" } }

try {
  Log "start (DryRun=$DryRun)"
  Set-Location -LiteralPath $RepoDir
  $target = "site/demo/mandi/live.js"
  $fetcher = Join-Path $RepoDir "site/demo/mandi/fetch_live.py"

  if (-not $DryRun) {
    Git fetch origin main
    Git checkout main
    Git pull --ff-only origin main
  }

  $out = if ($DryRun) { Join-Path $env:TEMP "vitastaiq_live_dryrun.js" } else { Join-Path $RepoDir $target }
  if ($DryRun -and (Test-Path $out)) { Remove-Item $out -Force }

  & $PythonExe -I $fetcher --env $EnvFile --out $out
  if ($LASTEXITCODE -ne 0) { Log "fetch did not produce usable data (exit $LASTEXITCODE); existing data kept"; exit 0 }

  $head = (Get-Content -LiteralPath $out -TotalCount 1)
  if ($head.Length -lt 5000 -or -not $head.StartsWith("window.LIVE=")) { throw "output file looks wrong; not publishing" }
  $m = [regex]::Match($head, '"date":"([^"]+)","fetched":"([^"]+)","rows":(\d+),"markets":(\d+),"states":(\d+)')
  Log ("fetched: data date {0}, {1} records, {2} markets, {3} states" -f $m.Groups[1].Value, $m.Groups[3].Value, $m.Groups[4].Value, $m.Groups[5].Value)

  if ($DryRun) { Log "dry run: nothing committed or pushed"; Remove-Item $out -Force; exit 0 }

  Git add -- $target
  Git commit -m ("Refresh live mandi data ({0})" -f $m.Groups[1].Value) -- $target
  Git push origin main
  Log "published; GitHub will redeploy the site in about a minute"
}
catch {
  Log ("ERROR: " + $_.Exception.Message)
  exit 1
}
