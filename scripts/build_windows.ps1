# Build VectorForge Windows .exe (PowerShell)
# Run from anywhere; switches to repo root.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "=== VectorForge Windows build ==="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

Write-Host "=== Smoke test ==="
python -m vectorforge.cli --help

Write-Host "=== PyInstaller ==="
python -m PyInstaller --noconfirm VectorForge.spec

Write-Host ""
Write-Host "Build complete: dist\VectorForge.exe"
Get-Item "dist\VectorForge.exe" | Format-List Name, Length, LastWriteTime
