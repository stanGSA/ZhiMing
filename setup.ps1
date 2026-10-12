$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.python-runtimes'
$uvExecutable = Join-Path $PSScriptRoot '.bootstrap\Scripts\uv.exe'
if (-not (Test-Path -LiteralPath $uvExecutable)) {
    python -m venv .bootstrap
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create bootstrap environment' }
    & '.\.bootstrap\Scripts\python.exe' -m pip install 'uv==0.13.0'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install uv' }
}
& $uvExecutable sync --locked --extra llm
if ($LASTEXITCODE -ne 0) { throw 'Failed to synchronize project environment' }
& '.\.venv\Scripts\python.exe' -m knowledge.build
if ($LASTEXITCODE -ne 0) { throw 'Failed to build knowledge base' }
& '.\.venv\Scripts\python.exe' -m scripts.fetch_data
if ($LASTEXITCODE -ne 0) { throw 'Failed to verify data manifest' }
& '.\.venv\Scripts\python.exe' -m scripts.doctor
if ($LASTEXITCODE -ne 0) { throw 'Environment diagnostics failed' }
