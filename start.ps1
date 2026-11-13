$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$worker = Start-Process -FilePath $pythonPath -ArgumentList @("manage.py", "process_no_shows", "--watch") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
try {
    & $pythonPath manage.py runserver 127.0.0.1:8000
} finally {
    if (-not $worker.HasExited) { & taskkill /PID $worker.Id /T /F | Out-Null }
}
