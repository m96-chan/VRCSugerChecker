@echo off
REM ===============================================
REM VRChat Sugar Checker - Build Script (Windows)
REM ===============================================
echo VRChat Sugar Checker - Complete Build
echo ======================================
echo.

REM Step 1: Build C++ Native Extension
echo [1/2] Building C++ Native Extension...
echo.
call build_native.bat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Native extension build failed!
    pause
    exit /b 1
)

echo.
echo [2/2] Building Executable with PyInstaller...
echo.

REM Check if PyInstaller is installed
uv run pyinstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller is not installed!
    echo Please run: uv add --dev pyinstaller
    pause
    exit /b 1
)

REM Clean previous build
if exist dist\VRChatSugarChecker.exe del /q dist\VRChatSugarChecker.exe
if exist build\VRChatSugarChecker rmdir /s /q build\VRChatSugarChecker

REM Build executable
cd build
uv run pyinstaller --distpath ../dist --workpath ../build/build VRChatSugarChecker.spec
cd ..

if exist dist\VRChatSugarChecker.exe (
    echo.
    echo ======================================
    echo Build Successful!
    echo ======================================
    echo.
    echo Executable: dist\VRChatSugarChecker.exe
    echo.
    echo Next steps:
    echo 1. Test: dist\VRChatSugarChecker.exe
    echo 2. Install startup: powershell -ExecutionPolicy Bypass -File install_startup.ps1
    echo.
) else (
    echo.
    echo ERROR: Build failed! Executable not found.
    echo.
)

pause
