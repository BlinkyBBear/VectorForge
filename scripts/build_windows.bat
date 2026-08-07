@echo off
REM Build VectorForge Windows .exe with PyInstaller
REM Run from repo root on a Windows machine with Python 3.10+ installed.
setlocal
cd /d "%~dp0\.."

echo === VectorForge Windows build ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo === Smoke test engine ===
python -m vectorforge.cli --help
if errorlevel 1 exit /b 1

echo === PyInstaller ===
python -m PyInstaller --noconfirm VectorForge.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete.
echo   dist\VectorForge.exe
echo.
echo First launch may download the rembg u2net model (~176MB) into %%USERPROFILE%%\.u2net
echo After that the app is fully offline.
echo.
dir dist\VectorForge.exe
endlocal
