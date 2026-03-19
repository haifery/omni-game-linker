# Building Omni Game Linker

This document walks through producing a distributable Windows installer
from the source code. No prior packaging experience needed.

---

## What you'll need

| Tool | Where to get it | Why |
|---|---|---|
| Python 3.11+ | https://python.org/downloads | Runs the app and build tools |
| PyInstaller | `pip install pyinstaller` | Bundles Python into a .exe |
| Inno Setup 6 | https://jrsoftware.org/isinfo.php | Wraps the .exe in a proper installer |
| UPX *(optional)* | https://github.com/upx/upx/releases | Compresses the .exe (smaller download) |

---

## Repo layout

```
omni-game-linker/
├── omni_game_linker.py      ← main source file
├── omni_game_linker.spec    ← PyInstaller config
├── assets/
│   └── icon.ico              ← app icon (add your own)
├── installer/
│   ├── setup.iss             ← Inno Setup script
│   └── Output/               ← installer .exe lands here (git-ignored)
└── dist/                     ← PyInstaller output lands here (git-ignored)
```

---

## Step 1 — Install Python dependencies

Open a terminal in the repo root and run:

```
pip install customtkinter pyinstaller
```

---

## Step 2 — (Optional) Add an icon

Create or find a `.ico` file and save it to `assets\icon.ico`.

Then in `omni_game_linker.spec`, uncomment:
```python
icon='assets\\icon.ico',
```

And in `installer\setup.iss`, the `SetupIconFile` line is already pointing
to `assets\icon.ico` — comment it out if you don't have one yet:
```ini
; SetupIconFile=..\assets\icon.ico
```

---

## Step 3 — (Optional) Add Windows version info

This makes the .exe show proper metadata in Properties → Details (version,
company name, etc).

Create a file called `version_info.txt` in the repo root:

```
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 2, 0, 0),
    prodvers=(1, 2, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName',      u'YourNameHere'),
         StringStruct(u'FileDescription',  u'Omni Game Linker'),
         StringStruct(u'FileVersion',      u'1.2.0.0'),
         StringStruct(u'InternalName',     u'OmniGameLinker'),
         StringStruct(u'LegalCopyright',   u'Copyright 2025 YourNameHere'),
         StringStruct(u'OriginalFilename', u'OmniGameLinker.exe'),
         StringStruct(u'ProductName',      u'Omni Game Linker'),
         StringStruct(u'ProductVersion',   u'1.2.0.0')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
```

Then in `omni_game_linker.spec`, uncomment:
```python
version='version_info.txt',
```

---

## Step 4 — Build the .exe with PyInstaller

In the repo root:

```
pyinstaller omni_game_linker.spec
```

This produces `dist\OmniGameLinker.exe`.

You can test it by running `dist\OmniGameLinker.exe` directly before
going any further.

**Common issues:**

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` at runtime | Add the missing module to `hiddenimports` in the .spec file |
| App starts but looks wrong | Make sure `customtkinter` is installed in the same Python environment you ran PyInstaller from |
| File is very large (>30 MB) | Install UPX and re-run — the spec already enables UPX compression |

---

## Step 5 — Build the installer with Inno Setup

Before building, open `installer\setup.iss` and update these lines:

```ini
#define AppPublisher "YourNameHere"
AppPublisherURL=https://github.com/OWNER/omni-game-linker
AppSupportURL=https://github.com/OWNER/omni-game-linker/issues
AppUpdatesURL=https://github.com/OWNER/omni-game-linker/releases
```

The installer will default to `C:\Program Files\OmniGameLinker` and requires admin elevation. The user can change the path during install.

Then either:

**Option A — GUI:**
1. Open Inno Setup Compiler
2. File → Open → select `installer\setup.iss`
3. Build → Compile  (or press F9)

**Option B — Command line:**
```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
```

Output: `installer\Output\OmniGameLinker_Setup_v1.2.0.exe`

---

## Step 6 — Test the installer

1. Run `installer\Output\OmniGameLinker_Setup_v1.2.0.exe`
2. Go through the install wizard
3. Launch from Start Menu or Desktop shortcut
4. Verify the app opens correctly
5. Open Add/Remove Programs and confirm the uninstaller entry exists
6. Run the uninstaller and confirm it removes cleanly

---

## Bumping the version for a new release

1. Update `APP_VERSION` in `omni_game_linker.py`
2. Update `#define AppVersion` in `installer\setup.iss`
3. Update `version_info.txt` if you created one
4. Re-run Steps 4 and 5

---

## What gets left behind on uninstall

By design, the Inno Setup uninstaller removes only what it installed
(the `.exe` in Program Files and the Start Menu / Desktop shortcuts).

It intentionally leaves behind:
- `%APPDATA%\OmniGameLinker\config.json` — the user's settings

This is standard practice so users don't lose their preferences if they
reinstall. The app's own **Settings → Danger Zone → Uninstall app data**
option handles removing that folder if the user wants a clean slate.
