# Omni Game Linker

![Version](https://img.shields.io/badge/version-1.2.0-e94560)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Omni Game Linker** is a Windows desktop app that generates lightweight launcher `.exe` files for games across any platform — Steam, Epic Games, Xbox Game Pass, Prism Launcher, and more via a plugin system.

Built for use with frontends like **Decent Icons**, **Playnite**, or any launcher that requires a real `.exe` to represent a game.

---

## Features

- **Multi-platform import** — automatically scans and imports games from Steam, Epic Games, Xbox / PC Game Pass, and Prism Launcher
- **Plugin system** — extend support to any game store by dropping in a simple Python plugin
- **Single-file .exe output** — each generated launcher is a standalone `.exe` with no dependencies
- **Settings persistence** — accent colour, output directory, plugin path, and update preferences saved between sessions
- **Auto updater** — checks GitHub releases on startup and can download and install updates silently
- **Clean uninstall** — removes app data and optionally your generated output folder from within the app

---

## Installation

1. Download the latest installer from the [Releases](https://github.com/haifery/omni-game-linker/releases) page
2. Run `OmniGameLinker_Setup_vX.X.X.exe`
3. Follow the install wizard — installs to `C:\Program Files\Omni Game Linker`

**Requirements:** Windows 10 or later (64-bit). No Python or .NET installation required.

---

## Usage

### Basic workflow

1. **Add games** — type a game name and its Launch ID into a row, or click **⬇ Import Games...** to auto-import from your installed libraries
2. **Set output folder** — choose where your launcher `.exe` files will be saved
3. **Generate** — click **⚡ Generate All** and confirm folder names

### Launch ID formats

| Platform | Format | Example |
|---|---|---|
| Steam | Numeric App ID | `1091500` |
| Epic Games | `EPIC:<uri>` | `EPIC:com.epicgames.launcher://...` |
| Xbox / Game Pass | `XBOX:<uri>` | `XBOX:ms-xbl-3d8b930f://` |
| Prism Launcher | `PRISM:<id>\|<path>` | `PRISM:1.21.8\|C:\...\prismlauncher.exe` |
| Custom plugin | `PREFIX:<uri>` | `BNET:battlenet://WTCG` |

---

## Plugin System

Omni Game Linker can be extended to support any game store through plugins.

A plugin is a folder containing two files:

```
my-plugin/
├── plugin.json
└── my_plugin.py
```

**`plugin.json`**
```json
{
  "name": "My Store",
  "version": "1.0.0",
  "author": "yourname",
  "description": "Imports games from My Store",
  "entry": "my_plugin.py"
}
```

**`my_plugin.py`**
```python
# Required — return a list of (display_name, launch_id) tuples
def find_games():
    return [
        ("Game One", "MYSTORE:game_one_id"),
        ("Game Two", "MYSTORE:game_two_id"),
    ]

# Optional — claim a custom prefix
PREFIXES = ["MYSTORE"]

# Optional — custom exe compilation logic
# If omitted, the app strips the prefix and shell-executes the remainder as a URI
def create_exe(game_name, launch_id, output_dir, csc_path, debug=False):
    # return (exe_filename, None) on success
    # return (None, error_string) on failure
    ...
```

To install plugins, go to **Settings → Plugin Configuration**, point to your plugins folder, and click **Apply & Reload Plugins**. Each valid plugin adds an entry to the **⬇ Import Games...** menu automatically.

See [PLUGINS.md](PLUGINS.md) for a full authoring guide.

---

## Building from Source

See [BUILD.md](BUILD.md) for full instructions on building the `.exe` and installer from the Python source.

**Quick version:**
```
pip install customtkinter pyinstaller pillow
pyinstaller omni_game_linker.spec
# Then open installer/setup.iss in Inno Setup 6 and press F9
```

---

## Project Structure

```
omni-game-linker/
├── omni_game_linker.py     — main application
├── omni_game_linker.spec   — PyInstaller build config
├── assets/
│   ├── icon.ico            — app icon (multi-resolution)
│   └── icon_transparent.png — icon with transparent background (used in UI header)
├── installer/
│   └── setup.iss           — Inno Setup installer script
├── BUILD.md                — build instructions
├── PLUGINS.md              — plugin authoring guide
└── LICENSE                 — MIT
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
