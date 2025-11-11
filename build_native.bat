@echo off
echo Building WASAPI Process Loopback Native Extension...
echo.

REM ビルド前にクリーンアップ
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist wasapi_process_loopback_native.egg-info rmdir /s /q wasapi_process_loopback_native.egg-info

REM C++拡張をビルド
uv run python setup_native.py build_ext --inplace

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Build failed!
    echo.
    echo Please make sure you have:
    echo 1. Visual Studio Build Tools installed
    echo 2. Windows SDK installed
    echo.
    pause
    exit /b 1
)

echo.
echo Build successful!
echo.

REM .pydファイルを適切な場所に移動
echo Moving extension module to src\modules\audio\...

REM カレントディレクトリから移動
if exist wasapi_process_loopback_native*.pyd (
    move /y wasapi_process_loopback_native*.pyd src\modules\audio\
    echo - Moved from current directory
)

REM srcディレクトリから移動
if exist src\wasapi_process_loopback_native*.pyd (
    move /y src\wasapi_process_loopback_native*.pyd src\modules\audio\
    echo - Moved from src\ directory
)

REM buildディレクトリからコピー
if exist build\lib.win-amd64-cpython-313\wasapi_process_loopback_native*.pyd (
    copy /y build\lib.win-amd64-cpython-313\wasapi_process_loopback_native*.pyd src\modules\audio\
    echo - Copied from build directory
)

echo.
echo Extension module installed to: src\modules\audio\
dir /b src\modules\audio\wasapi_process_loopback_native*.pyd 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Installation successful!
) else (
    echo WARNING: Extension module not found in target directory!
)

echo.
pause
