# Changelog

All notable changes to Omni Game Linker will be documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] — 2026-03-19

### Added
- **Plugin system** — extend import support to any game store via Python plugins
  - `plugin.json` metadata + `find_games()` entry point
  - Optional `PREFIXES` to claim custom launch ID prefixes
  - Optional `create_exe()` for custom compilation logic
  - Generic shell-execute fallback for plugins without `create_exe`
  - Plugins appear automatically in the Import Games menu
- **Settings persistence** — accent colour, output directory, plugin directory, and update preferences now saved to `%APPDATA%\OmniGameLinker\config.json`
- **Update system** — automatic update checker on startup
  - Silent background check against GitHub releases API
  - Update & Restart Now — downloads and installs silently with progress bar
  - Download & Update on Next Launch — saves installer for next startup
  - Open Releases Page — opens browser to GitHub releases
  - Don't Ask Again — suppresses startup prompt, re-enable in Settings
  - Manual Check for Updates button in Version dialog
- **Unified Import menu** — all import sources consolidated into a single ⬇ Import Games... dropdown button
- **Threaded imports** — all platform scans run on background threads, UI stays responsive during scanning
- **Search in import dialogs** — live search filter in all import checklists
- **Uninstall feature** — Settings → Danger Zone
  - Removes app data folder
  - Optionally deletes generated output folder
  - Detects and launches Windows uninstaller when running as installed app
- **Header icon** — app icon displayed in the title bar with transparent background
- **Taskbar/titlebar icon** — correct icon shown in window chrome and taskbar
- **Column headers** — Game Name column now flexes with window width
- **Settings cards** — Appearance, Plugin Configuration, Update Preferences, and Danger Zone sections
- **Sticky Save/Close footer** in Settings — always visible while scrolling
- **VDF parser hardening** — unknown type bytes skipped rather than aborting parse

### Changed
- Import buttons replaced with unified ⬇ Import Games... dropdown menu
- Settings window redesigned with card-based layout
- Help text updated to cover plugins, update system, and ID formats
- Version dialog expanded with runtime info and update check button
- Default install location set to `C:\Program Files\Omni Game Linker`

### Fixed
- Column header widths now align correctly with row entry fields at all window sizes
- Xbox import loop no longer redundantly re-packs the Add Row button on every game added
- Blank placeholder row correctly consumed before any import populates rows

---

## [1.1.0] — Initial private build

### Added
- Steam library import (shortcuts.vdf parser + installed games scan)
- Epic Games import (manifest file parser)
- Xbox / PC Game Pass import (AppxManifest.xml scanner with PowerShell fallback)
- Prism Launcher import (instance.cfg scanner)
- Multi-resolution .ico support (16×16 through 256×256)
- Accent colour presets (Red, Blue, Green, Purple, Orange)
- Debug mode (shows csc.exe console during generation)
- Auto-confirm All in folder name dialog
- Per-row remove button with row renumbering
- Clear All button
- Help dialog with step-by-step usage guide
- Version dialog with runtime info
- Log panel with colour-coded output (ok / err / info)
- Uncaught exception handler routing to log panel

---

## Note for Future haifery

When releasing a new version:

1. Add a new `## [X.Y.Z] — YYYY-MM-DD` section at the top of this file
2. Use these categories as needed:
   - `Added` — new features
   - `Changed` — changes to existing behaviour
   - `Fixed` — bug fixes
   - `Removed` — features removed
   - `Security` — security fixes
3. Update `APP_VERSION` in `omni_game_linker.py`
4. Update `#define AppVersion` in `installer/setup.iss`
5. Rebuild with PyInstaller + Inno Setup
6. Push, tag, and create a GitHub release with the installer attached
