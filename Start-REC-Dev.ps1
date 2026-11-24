$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not (Test-Path (Join-Path $root 'package.json'))) {
    $root = Join-Path $root 'React REC'
}
$apiUrl = 'http://127.0.0.1:8771/'
$uiUrl = 'http://127.0.0.1:8767/'

Set-Location $root
$python = (Get-Command python -ErrorAction Stop).Source

$apiReady = $false
try {
    $response = Invoke-WebRequest $apiUrl -UseBasicParsing -TimeoutSec 2
    $apiReady = $response.StatusCode -eq 200
} catch { }

if (-not $apiReady) {
    Start-Process -FilePath $python `
        -ArgumentList @('-B', '-X', 'utf8', 'server.py') `
        -WorkingDirectory $root `
        -WindowStyle Hidden | Out-Null
}

$viteCommand = "Set-Location -LiteralPath '$root'; npm run dev"
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $viteCommand) `
    -WorkingDirectory $root | Out-Null

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $page = Invoke-WebRequest $uiUrl -UseBasicParsing -TimeoutSec 2
        if ($page.StatusCode -eq 200) {
            Start-Process $uiUrl
            Write-Host "REC dev is ready: $uiUrl"
            exit 0
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}

throw 'Vite failed to start on port 8767.'
