# -*- mode: python ; coding: utf-8 -*-
"""
VRChat Sugar Checker - PyInstaller設定ファイル
"""

block_cipher = None

# 分析: 必要なファイルとモジュールを収集
a = Analysis(
    ['../src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 設定ファイルのサンプルを含める
        ('../config.example.json', '.'),
        # modulesフォルダを含める
        ('../src/modules', 'modules'),
    ],
    hiddenimports=[
        'requests',
        'logging.handlers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PYZアーカイブの作成
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 実行ファイルの作成
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
    upx=True,  # UPX圧縮を有効化（ファイルサイズを削減）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # コンソールウィンドウを表示（デバッグ用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # アイコンファイル（オプション）
    # icon='icon.ico',
)
