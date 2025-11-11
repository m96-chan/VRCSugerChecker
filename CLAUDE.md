# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation Structure

- **README.md**: ユーザー向けドキュメント（機能説明、インストール、使い方）
- **DEVELOPMENT.md**: 開発者向けドキュメント（アーキテクチャ、開発環境、実装詳細）
- **CLAUDE.md**: このファイル（Claude Code向けの技術ガイド）
- **docs/**: 詳細ドキュメント
  - **BUILD_GUIDE.md**: ビルド手順
  - **RELEASE_GUIDE.md**: リリース手順
  - **AUDIO_RECORDING.md**: 音声録音機能の詳細

## Project Overview

VRChat Sugar Checker is a Windows process monitoring tool that watches VRChat.exe execution and automatically parses VRChat logs to track instance information, user joins/leaves, and send Discord notifications. It runs in the background on Windows (developed in WSL2) and includes audio recording, screenshot capture, and file upload capabilities.

## Development Environment

- **Platform**: Windows 10/11 (WSL2 for development)
- **Python**: 3.13+ (see `.python-version`)
- **Package Manager**: uv (project uses `uv.lock` and `pyproject.toml`)

### Running Commands

```bash
# Run the application (must have access to Windows processes)
uv run python main.py

# Run with custom config
uv run python main.py --config config.json

# Run with custom check interval
uv run python main.py --interval 10

# Install dependencies
uv sync
# or
pip install -r requirements.txt

# Build C++ native extension (required first time and after C++ changes)
build_native.bat      # Windows
./build_native.bat    # WSL (calls Windows bat file)

# Build complete application (includes native extension + executable)
build.bat             # Windows
./build.sh            # Linux/WSL
```

## Project Structure

```
VRCSugerChecker/
├── src/                          # Source code
│   ├── main.py                   # Main entry point
│   └── modules/                  # Feature modules
│       ├── vrc/                  # VRChat log parsing
│       ├── discord/              # Discord webhook notifications
│       ├── screenshot/           # Screenshot capture
│       └── audio/                # Audio recording
│           ├── recorder.py       # Main audio recorder
│           ├── wasapi_process_loopback.py         # Pure Python WASAPI (fallback)
│           └── wasapi_process_loopback_native.cpp # C++ native extension
├── build/                        # Build configuration
│   └── VRChatSugarChecker.spec   # PyInstaller spec
├── docs/                         # Documentation
│   ├── AUDIO_RECORDING.md
│   ├── BUILD_GUIDE.md
│   └── RELEASE_GUIDE.md
├── logs/                         # Runtime logs and captures
├── build_native.bat              # Build C++ native extension
├── setup_native.py               # C++ extension build config
├── build.bat, build.sh           # Complete build scripts
├── run_silent.vbs                # Silent launcher
├── install_startup.ps1           # Startup installer
├── uninstall_startup.ps1         # Startup uninstaller
├── config.example.json           # Configuration template
└── README.md, CLAUDE.md          # Project documentation
```

## Architecture Overview

### Core Components

1. **Process Monitor** (`src/main.py:181-246`)
   - Monitors VRChat.exe using PowerShell commands
   - Detects VRChat start/stop events
   - Triggers log monitoring when VRChat is running
   - Main loop in `monitor_vrchat_process()` function

2. **Log Parser** (`src/modules/vrc/parse_logs.py`)
   - Parses VRChat log files from `AppData/LocalLow/VRChat/VRChat`
   - Extracts instance IDs, world names, and user join/leave events
   - Patterns: `OnPlayerJoined`, `OnPlayerLeft`, `Entering Room`, `Joining`
   - Detects microphone device from VRChat logs (src/main.py:269-271)

3. **Discord Notifier** (`src/modules/discord/webhook.py`)
   - Sends Discord webhook notifications for events
   - Features user profile links and instance launch links
   - Handles Discord field length limits by splitting user lists

4. **Screenshot Capture** (`src/modules/screenshot/capture.py`)
   - Captures VRChat window using Win32 API or PowerShell fallback
   - Supports auto-capture at intervals (default: 3 minutes)
   - Captures on instance change with 2-second delay for loading
   - Saves to `logs/screenshots/`

5. **Audio Recorder** (`src/modules/audio/recorder.py`)
   - **VRChat Process-Specific Audio**: Uses C++ native WASAPI extension to capture ONLY VRChat audio
   - **Fallback Options**: Pure Python WASAPI → PyAudioWPatch → System-wide capture
   - **Native Extension**: `wasapi_process_loopback_native.cpp` compiled as Python module
   - Implements Windows WASAPI `ActivateAudioInterfaceAsync` API with Process Loopback
   - Requires Windows 10 Build 20438+ for process-specific capture
   - Records microphone input separately using sounddevice
   - Merges VRChat audio + microphone using FFmpeg
   - Outputs to `logs/audio/` with world ID in filename
   - Automatically starts/stops based on world changes

### State Management

Global state tracking in `src/main.py`:
- `last_instance_id`: Tracks current VRChat instance
- `last_users`: Dict of users in current instance (display_name → user_id)
- `last_world_name`: Current world name for change detection
- `discord_webhook`, `screenshot_capture`, `audio_recorder`: Module instances

State changes trigger different actions:
- **Instance change**: Discord notification, screenshot capture, audio recording restart
- **User join/leave**: Discord notifications (if enabled)
- **World change**: Audio recording restart

### Configuration System

Configuration loaded from `config.json` (see `config.example.json`):
- **discord**: Webhook URL and notification toggles
- **monitoring**: Check intervals (process: 5s, log update: 30s)
- **audio**: Recording settings, device, format (m4a), retention (7 days)
- **screenshot**: Auto-capture settings, triggers, retention (7 days)
- **logs**: Text log retention (7 days)

Settings are accessed via nested dict gets: `config.get("discord", {}).get("notifications", {}).get("user_joined", False)`

### File Management

- **Log rotation**: 7-day rotation using `TimedRotatingFileHandler` (src/main.py:38-83)
- **Cleanup**: Old logs/audio/screenshots deleted on startup (src/main.py:86-112)
- **Paths**: All logs stored under `logs/` directory with subdirs for audio and screenshots

## WSL Environment Handling

The tool detects WSL by checking for "microsoft" in `platform.release()` and constructs Windows paths:
- WSL path: `/mnt/c/Users/{username}/AppData/LocalLow/VRChat/VRChat`
- Uses `WINDOWS_USER` environment variable if set
- Executes PowerShell commands from WSL for process monitoring

## Build System

The project uses a two-stage build process:

### Stage 1: C++ Native Extension

**Required for VRChat-only audio capture**

```bash
# Build C++ extension
build_native.bat      # Windows
./build_native.bat    # WSL
```

Requirements:
- Visual Studio Build Tools 2022+ with C++ support
- Windows SDK 10.0.22000.0+
- Compiles to: `src/modules/audio/wasapi_process_loopback_native*.pyd`

Build configuration: `setup_native.py`
- Uses setuptools Extension
- C++20 standard (`/std:c++20`)
- Links: ole32, uuid, propsys
- Implements IAgileObject for thread marshaling

### Stage 2: PyInstaller Executable

```bash
# Complete build (native extension + executable)
build.bat             # Windows
./build.sh            # Linux/WSL

# Manual PyInstaller build
cd build
uv run pyinstaller VRChatSugarChecker.spec
```

Build spec file: `build/VRChatSugarChecker.spec`
- References source from `../src/main.py`
- Includes modules from `../src/modules`
- Bundles native extension (.pyd file)
- Output: `dist/VRChatSugarChecker.exe` with all dependencies

### Build Troubleshooting

**Native extension build fails:**
1. Install Visual Studio Build Tools
2. Install Windows SDK
3. Ensure MSVC compiler is in PATH

**PyInstaller missing native extension:**
1. Run `build_native.bat` first
2. Verify .pyd file exists in `src/modules/audio/`
3. Rebuild with `build.bat` or `build.sh`

## Deployment

Windows startup integration:
- `install_startup.ps1`: Registers VBS script in Windows startup folder
- `run_silent.vbs`: Launches executable without console window
- `uninstall_startup.ps1`: Removes startup registration

Installation steps:
```powershell
# Build application
.\build.bat

# Install to startup
powershell -ExecutionPolicy Bypass -File install_startup.ps1
```

## Important Implementation Details

### VRChat Log Parsing

The log parser maintains user state by:
1. Clearing user list on instance change (src/modules/vrc/parse_logs.py:143-151)
2. Adding users on `OnPlayerJoined` events
3. Removing users on `OnPlayerLeft` events
4. Timestamp extraction for event ordering

Instance changes are detected when the `Joining` pattern shows a new instance ID different from `current_instance`.

### Audio Recording Flow

1. **VRChat Process Detection**: Find VRChat.exe PID using pycaw AudioUtilities
2. **Native Extension Initialization**: Create ProcessLoopback object with VRChat PID
3. **Process-Specific Capture**:
   - Try `ActivateAudioInterfaceAsync` with `AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`
   - Requires Windows 10 Build 20438+, STA thread, IAgileObject implementation
   - Falls back to system-wide capture if fails
4. **Microphone Recording**: Separate sounddevice recording of mic input
5. **Audio Merging**: FFmpeg merges VRChat audio + mic with `amix` filter
6. **File Output**: Saves as WAV to `logs/audio/{world_id}-{timestamp}_{vrchat|mic}.wav`
7. **Cleanup**: Merges and deletes source files (unless `keep_source_files` is true)

### Screenshot Capture Timing

- **Instance change**: 2-second delay to allow world loading (src/modules/screenshot/capture.py:303)
- **Auto-capture**: Runs in background thread with configurable interval
- **VRChat start**: Immediate capture if enabled

### Discord Webhook Considerations

- User lists split into multiple fields if >900 chars (src/modules/discord/webhook.py:161-215)
- Instance links use `https://vrchat.com/home/launch?worldId=` with URL encoding
- All notifications include UTC timestamps and consistent footer

## Testing Considerations

When testing or debugging:
- VRChat.exe must be running for process detection
- VRChat logs must exist in AppData folder
- FFmpeg must be installed in PATH for audio recording
- Windows API (`pywin32`, `Pillow`) needed for screenshot capture
- Discord webhook URL must be valid for notifications

## Dependencies

Core libraries (from `pyproject.toml`):
- `requests`: Discord webhook HTTP requests
- `pywin32`: Windows API access, COM for audio session management
- `pillow`: Image processing for screenshots
- `sounddevice`, `soundfile`: Microphone recording
- `numpy`: Audio data processing
- `pycaw`: Windows Audio Session API (WASAPI) wrapper
- `comtypes`: COM interface access for WASAPI
- `pyaudiowpatch`: WASAPI loopback fallback (optional)

Build dependencies:
- Visual Studio Build Tools 2022+ (MSVC compiler)
- Windows SDK 10.0.22000.0+
- PyInstaller (for executable builds)

External:
- FFmpeg: Audio mixing and encoding (not Python package)

## Common Operations

### Adding New Event Types

1. Add regex pattern in `src/modules/vrc/parse_logs.py`
2. Add event detection in log parsing loop
3. Add Discord webhook method in `src/modules/discord/webhook.py`
4. Call webhook method from `src/main.py` monitoring functions

### Modifying Notification Settings

All notifications controlled by config flags in `config.json`:
- Check `config.get("discord", {}).get("notifications", {}).get("event_name")`
- Add new notification types to `config.example.json` and update README

### File Retention Changes

Modify `retention_days` in config for:
- Text logs: `logs.retention_days`
- Audio: `audio.retention_days`
- Screenshots: `screenshot.retention_days`

Cleanup runs on startup via `cleanup_old_*()` functions.
