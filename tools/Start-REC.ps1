$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$serverFile = Join-Path $root 'server.py'
$url = 'http://127.0.0.1:8771/'
Set-Location $root

try {
    $python = (Get-Command python -ErrorAction Stop).Source
    $toStop = @()
    $keep = $false
    foreach ($port in @(8768, 8771)) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($owner in $listeners) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owner"
            if ($proc.Name -notmatch '^python(w|[0-9.]*)?\.exe$' -or $proc.CommandLine -notmatch 'server\.py') {
                throw "Port $port belongs to another application. Nothing was stopped."
            }
            $page = Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5
            if ($page.Content -notmatch '<title>REC') {
                throw "Port $port is not a verified REC server. Nothing was stopped."
            }
            $serverSources = @($serverFile, (Join-Path $root 'preview_cache.py'), (Join-Path $root 'row_locations.py'), (Join-Path $root 'ocr_quality.py'), (Join-Path $root 'dist/index.html'))
            $sourceChanged = @($serverSources | Get-Item | Where-Object { $_.LastWriteTime -gt $proc.CreationDate }).Count -gt 0
            if ($port -eq 8771 -and $listeners.Count -eq 1 -and $proc.CommandLine.IndexOf($serverFile, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and -not $sourceChanged) {
                $keep = $true
                continue
            }
            $status = Invoke-RestMethod "http://127.0.0.1:$port/api/ocr/status" -TimeoutSec 5
            if ($status.job.status -in @('importing', 'running')) {
                throw "REC on port $port is processing OCR. Wait until it finishes, then open REC again."
            }
            $toStop += $owner
        }
    }
    foreach ($owner in ($toStop | Select-Object -Unique)) {
        Stop-Process -Id $owner -Confirm:$false -Force -ErrorAction Stop
        Wait-Process -Id $owner -Timeout 10 -ErrorAction SilentlyContinue
    }
    if (-not $keep) {
        $child = Start-Process -FilePath $python -ArgumentList @('-B', '-X', 'utf8', ('"' + $serverFile + '"')) -WorkingDirectory $root -PassThru
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $page = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2
            if ($page.StatusCode -eq 200 -and $page.Content -match '<title>REC') { $ready = $true; break }
        } catch { }
        if ($child -and $child.HasExited) { throw 'REC could not start. Check the Python server window.' }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'REC did not become ready on port 8771. Check the Python server window.' }
    Start-Process $url
    Write-Host "REC is ready: $url"
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
