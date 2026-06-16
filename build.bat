@echo off
chcp 65001 >nul
echo ========================================
echo  BossKey Build Script
echo ========================================
echo.

pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing pyinstaller...
    pip install pyinstaller
)

echo [BUILD] Packaging BossKey.exe...
python -m PyInstaller build.spec --clean

if %errorlevel% equ 0 (
    echo.
    echo ======== BUILD SUCCESS ========
    echo Output: dist\BossKey.exe
    echo.
    echo NOTE:
    echo   - Run BossKey.exe AS ADMINISTRATOR
    echo   - config\ folder auto-created next to .exe
    echo ================================
) else (
    echo.
    echo [ERROR] Build failed - check log above
)
pause
