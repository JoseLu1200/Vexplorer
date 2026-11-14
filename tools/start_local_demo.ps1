param([switch]$Restart)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $repo '.runtime/localhost-production'
$python = Join-Path $repo '.venv/Scripts/python.exe'
$listener = Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
if ($listener) {
    if (-not $Restart) { Write-Output 'Demo already listening: https://localhost:8765'; return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if ($process.CommandLine -notlike '*uvicorn backend.app.main:app*localhost-production*') { throw 'Port 8765 belongs to another service.' }
    Stop-Process -Id $listener.OwningProcess
}
foreach ($file in @($python, (Join-Path $runtime 'key.pem'), (Join-Path $runtime 'cert.pem'), (Join-Path $runtime 'catalog.json'))) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing prepared demo asset: $file" }
}
$env:VEXPLORER_ENV='production'
$env:VEXPLORER_AUTH_ENABLED='false'
$env:VEXPLORER_ALLOWED_ORIGINS='https://localhost:8765,https://127.0.0.1:8765'
$env:VEXPLORER_DATA_DIR=(Join-Path $runtime 'data')
$env:VEXPLORER_COST_CATALOG=(Join-Path $runtime 'catalog.json')
$env:VEXPLORER_ROOT_PATH=''
$env:OPENAI_MODEL='gpt-6.1-sol'
$env:OPENAI_MAX_OUTPUT_TOKENS='16384'
$env:OPENAI_VISION_ENABLED='true'
$env:VEXPLORER_GENERAL_REVIEW_MODEL='gpt-6-astra'
$env:VEXPLORER_DWG_CONVERTER='libredwg'
$env:VEXPLORER_DWG2DXF_EXECUTABLE=(Join-Path $repo '.runtime/libredwg-0.14/bin/dwg2dxf.exe')
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$process=Start-Process -FilePath $python -ArgumentList '-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env --ssl-keyfile .runtime/localhost-production/key.pem --ssl-certfile .runtime/localhost-production/cert.pem' -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "server-$stamp.out.log") -RedirectStandardError (Join-Path $runtime "server-$stamp.err.log") -PassThru
Write-Output "Started demo launcher PID $($process.Id): https://localhost:8765"
