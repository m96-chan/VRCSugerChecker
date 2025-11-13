#!/bin/bash
# ===============================================
# VRChat Sugar Checker - Build Script (Linux/WSL)
# ===============================================

set -e

echo "VRChat Sugar Checker - Complete Build"
echo "======================================"
echo

# Step 1: Build C++ Native Extension
echo "[1/2] Building C++ Native Extension..."
echo
./build_native.bat

echo
echo "[2/2] Building Executable with PyInstaller..."
echo

# Check if PyInstaller is installed
if ! uv run pyinstaller --version >/dev/null 2>&1; then
    echo "ERROR: PyInstaller is not installed!"
    echo "Please run: uv add --dev pyinstaller"
    exit 1
fi

# Clean previous build
rm -f dist/VRChatSugarChecker.exe
rm -rf build/VRChatSugarChecker

# Build executable
cd installer
uv run pyinstaller --distpath ../dist --workpath ../build/build VRChatSugarChecker.spec
cd ..

if [ -f dist/VRChatSugarChecker.exe ]; then
    echo
    echo "======================================"
    echo "Build Successful!"
    echo "======================================"
    echo
    echo "Executable: dist/VRChatSugarChecker.exe"
    echo
    echo "Next steps:"
    echo "1. Test: dist/VRChatSugarChecker.exe"
    echo "2. Install startup: powershell -ExecutionPolicy Bypass -File install_startup.ps1"
    echo
else
    echo
    echo "ERROR: Build failed! Executable not found."
    echo
    exit 1
fi
