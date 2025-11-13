# -*- mode: python ; coding: utf-8 -*-
# VRChat Sugar Checker - PyInstaller Build Specification

import os
import sys

# Get project root directory (parent of installer/)
SPEC_DIR = os.path.abspath(SPECPATH)
PROJECT_ROOT = os.path.dirname(SPEC_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

# Collect all Python modules
hiddenimports = [
    'win32com.client',
    'win32com.server',
    'win32api',
    'win32con',
    'win32gui',
    'win32ui',
    'win32process',
    'pywintypes',
    'comtypes',
    'comtypes.client',
    'pycaw',
    'sounddevice',
    'soundfile',
    'numpy',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'requests',
    'discord',
    'discord.ext',
    'discord.ext.commands',
    # VRC modules
    'modules.vrc.parse_logs',
    'modules.vsc_discord.webhook',
    'modules.vsc_discord.bot',
    'modules.vsc_discord.vrchat_audio_source',
    'modules.screenshot.capture',
    'modules.screenshot.avatar_detector',
    'modules.screenshot.avatar_presence_detector',
    'modules.audio.recorder',
    'modules.audio.wasapi_process_loopback',
    'modules.audio.audio_preprocessor',
    'modules.upload.uploader',
    'modules.ai.image_analyzer',
    'modules.ai.audio_analyzer',
    'modules.time_tracker',
]

# Collect data files
datas = []

# Collect binary files (native extensions)
binaries = []

# Find native extension (.pyd file)
native_extension_pattern = os.path.join(SRC_DIR, 'modules', 'audio', 'wasapi_process_loopback_native*.pyd')
import glob
for pyd_file in glob.glob(native_extension_pattern):
    binaries.append((pyd_file, 'modules/audio'))

a = Analysis(
    [os.path.join(SRC_DIR, 'main.py')],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VRChatSugarChecker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False to hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if available
)
