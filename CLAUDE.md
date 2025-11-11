# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VRChat Sugar Checker is a Windows process monitoring tool that watches VRChat.exe execution and automatically parses VRChat logs to track instance information, user joins/leaves, and send Discord notifications. It runs in the background on Windows (developed in WSL2) and includes audio recording and screenshot capture capabilities.

## Development Environment

- **Platform**: Windows 10/11 (WSL2 for development)
- **Python**: 3.13+ (see `.python-version`)
- **Package Manager**: uv (project uses `uv.lock` and `pyproject.toml`)

### Running Commands

```bash
# Run the application (must have access to Windows processes)
python main.py

# Run with custom config
python main.py --config config.json

# Run with custom check interval
python main.py --interval 10

# Install dependencies
uv sync
# or
pip install -r requirements.txt
```

## Architecture Overview

### Core Components

1. **Process Monitor** (`main.py:181-246`)
   - Monitors VRChat.exe using PowerShell commands
   - Detects VRChat start/stop events
   - Triggers log monitoring when VRChat is running
   - Main loop in `monitor_vrchat_process()` function

2. **Log Parser** (`submodules/vrc/parse_logs.py`)
   - Parses VRChat log files from `AppData/LocalLow/VRChat/VRChat`
   - Extracts instance IDs, world names, and user join/leave events
   - Patterns: `OnPlayerJoined`, `OnPlayerLeft`, `Entering Room`, `Joining`
   - Detects microphone device from VRChat logs (main.py:269-271)

3. **Discord Notifier** (`submodules/discord/webhook.py`)
   - Sends Discord webhook notifications for events
   - Features user profile links and instance launch links
   - Handles Discord field length limits by splitting user lists

4. **Screenshot Capture** (`submodules/screenshot/capture.py`)
   - Captures VRChat window using Win32 API or PowerShell fallback
   - Supports auto-capture at intervals (default: 3 minutes)
   - Captures on instance change with 2-second delay for loading
   - Saves to `logs/screenshots/`

5. **Audio Recorder** (`submodules/audio/recorder.py`)
   - Records audio using FFmpeg with DirectShow
   - Mixes system audio (Stereo Mixer) and microphone input
   - Outputs AAC-encoded m4a files
   - Saves to `logs/audio/` with world ID in filename
   - Automatically starts/stops based on world changes

### State Management

Global state tracking in `main.py`:
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

- **Log rotation**: 7-day rotation using `TimedRotatingFileHandler` (main.py:38-83)
- **Cleanup**: Old logs/audio/screenshots deleted on startup (main.py:86-112)
- **Paths**: All logs stored under `logs/` directory with subdirs for audio and screenshots

## WSL Environment Handling

The tool detects WSL by checking for "microsoft" in `platform.release()` and constructs Windows paths:
- WSL path: `/mnt/c/Users/{username}/AppData/LocalLow/VRChat/VRChat`
- Uses `WINDOWS_USER` environment variable if set
- Executes PowerShell commands from WSL for process monitoring

## Build System

The project uses PyInstaller to create standalone Windows executables:

```bash
# Build using scripts (recommended)
./build.sh    # Linux/WSL
build.bat     # Windows

# Manual build
pyinstaller VRChatSugarChecker.spec
```

Build spec file: `VRChatSugarChecker.spec`
Output: `dist/VRChatSugarChecker.exe` with bundled dependencies

## Deployment

Windows startup integration:
- `install_startup.ps1`: Registers VBS script in Windows startup folder
- `run_silent.vbs`: Launches Python script without console window
- `uninstall_startup.ps1`: Removes startup registration

## Important Implementation Details

### VRChat Log Parsing

The log parser maintains user state by:
1. Clearing user list on instance change (parse_logs.py:143-151)
2. Adding users on `OnPlayerJoined` events
3. Removing users on `OnPlayerLeft` events
4. Timestamp extraction for event ordering

Instance changes are detected when the `Joining` pattern shows a new instance ID different from `current_instance`.

### Audio Recording Flow

1. Microphone device detected from VRChat logs (main.py:269-271)
2. Recording starts when entering a world (if `auto_start` enabled)
3. On world change: Stop current recording → Start new recording with new world ID
4. FFmpeg command mixes stereo mixer + mic with `amix` filter (recorder.py:82-93)
5. Recording stops on VRChat exit (if `auto_stop` enabled)

### Screenshot Capture Timing

- **Instance change**: 2-second delay to allow world loading (capture.py:303)
- **Auto-capture**: Runs in background thread with configurable interval
- **VRChat start**: Immediate capture if enabled

### Discord Webhook Considerations

- User lists split into multiple fields if >900 chars (webhook.py:161-215)
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
- `pywin32`: Windows API access for process/window operations
- `pillow`: Image processing for screenshots
- External: FFmpeg (not Python package) for audio recording

## Common Operations

### Adding New Event Types

1. Add regex pattern in `parse_logs.py`
2. Add event detection in log parsing loop
3. Add Discord webhook method in `webhook.py`
4. Call webhook method from `main.py` monitoring functions

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
