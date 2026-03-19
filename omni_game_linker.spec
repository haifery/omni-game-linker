# omni_game_linker.spec
# PyInstaller build specification for Omni Game Linker
#
# Usage:
#   pyinstaller omni_game_linker.spec
#
# Output:
#   dist\OmniGameLinker.exe

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ['omni_game_linker.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the assets folder so the header icon and exe icon are available at runtime
        ('assets', 'assets'),
    ],
    hiddenimports=[
        # customtkinter loads some things dynamically
        'customtkinter',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.messagebox',
        # PIL for loading the header icon
        'PIL',
        'PIL.Image',
        'PIL.IcoImagePlugin',
        # Standard lib used at runtime
        'importlib.util',
        'xml.etree.ElementTree',
        'struct',
        'json',
        'threading',
        'queue',
        'webbrowser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused heavy stdlib modules to keep the exe smaller
        'unittest',
        'email',
        'http',
        'urllib',
        'xmlrpc',
        'pydoc',
        'doctest',
        'difflib',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OmniGameLinker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # Compress with UPX if available — reduces file size
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # No console window (equivalent to --noconsole)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # ── Icon ──────────────────────────────────────────────────────────────
    icon='assets\\icon.ico',
    #
    # Version info embedded in the .exe (shows in Properties → Details)
    # Uncomment once you create version_info.txt (see BUILD.md):
    # version='version_info.txt',
)
