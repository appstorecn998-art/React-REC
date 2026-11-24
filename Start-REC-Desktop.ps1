$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
try {
    $pythonCommand = (Get-Command python -ErrorAction Stop).Source
    $python = (& $pythonCommand -c 'import sys; print(sys.executable)' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Python runtime was not found.' }
    $pythonw = Join-Path (Split-Path $python -Parent) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw = $python }
    $log = Join-Path $root 'output\desktop-startup-error.log'
    $child = Start-Process -FilePath $pythonw -ArgumentList @('-B', '-X', 'utf8', ('"' + (Join-Path $root 'desktop.py') + '"')) -WorkingDirectory $root -RedirectStandardError $log -PassThru
    if ($child.WaitForExit(4000) -and $child.ExitCode -ne 0) {
        $detail = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
        throw ('REC exited during startup. ' + $detail)
    }
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(('Cannot start React REC. ' + $_.Exception.Message), 'React REC') | Out-Null
    exit 1
}
