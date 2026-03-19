# Plugin Authoring Guide

This guide covers everything you need to know to write a plugin for **Omni Game Linker**.

Plugins let you add import support for any game store or launcher not built into the app. Once installed, your plugin appears automatically in the **⬇ Import Games...** menu.

---

## What a plugin can do

- **Scrape a game library** — return a list of games for the user to import
- **Claim a custom launch prefix** — so the app knows how to route your game IDs at compile time
- **Provide custom `.exe` compilation logic** — for launchers that need more than a simple shell-execute URI

---

## File structure

A plugin is a folder containing exactly two files:

```
my-plugin/
├── plugin.json
└── my_plugin.py
```

Place this folder inside your configured **Plugin Directory** (Settings → Plugin Configuration).

---

## plugin.json

```json
{
  "name":        "My Store",
  "version":     "1.0.0",
  "author":      "yourname",
  "description": "Imports games from My Store",
  "entry":       "my_plugin.py"
}
```

| Field | Required | Description |
|---|---|---|
| `name` | ✅ | Display name shown in the Import menu and plugin list |
| `version` | ✅ | Plugin version string |
| `author` | ✅ | Your name or handle |
| `description` | ✅ | Short description shown in the plugin list |
| `entry` | ✅ | Filename of your Python script (must be inside the plugin folder) |

---

## my_plugin.py

### Required — `find_games()`

This is the only function your plugin **must** implement. It is called when the user clicks your plugin's entry in the Import menu.

```python
def find_games() -> list[tuple[str, str]]:
    """
    Return a list of (display_name, launch_id) tuples.
    display_name — shown to the user in the import checklist
    launch_id    — stored in the ID field of the row
    """
    return [
        ("Game One", "MYSTORE:game_one_uri"),
        ("Game Two", "MYSTORE:game_two_uri"),
    ]
```

**Rules:**
- Must return a `list` of `(str, str)` tuples
- If no games are found, return an empty list `[]` — do not raise
- Exceptions are caught by the app, but try to handle your own errors gracefully
- The function runs on a background thread — do not interact with the UI from inside it

---

### Optional — `PREFIXES`

Declare a list of uppercase prefix strings your plugin owns. This tells the app how to route your launch IDs when generating `.exe` files.

```python
PREFIXES = ["MYSTORE"]
```

**Rules:**
- Must be a list of strings
- Prefixes are case-insensitive — `MYSTORE`, `mystore`, and `MyStore` are all treated as `MYSTORE`
- Do not include the colon — `"MYSTORE"` not `"MYSTORE:"`
- If two plugins claim the same prefix, the last one loaded wins (a warning is logged)

If you declare a prefix but do **not** implement `create_exe`, the app will strip your prefix and shell-execute the remainder as a URI. This works for any standard `protocol://` style URI automatically.

---

### Optional — `create_exe()`

Only needed if your launcher requires something more complex than a shell-execute URI — for example, if it needs command-line arguments or special invocation logic.

```python
def create_exe(
    game_name:  str,
    launch_id:  str,
    output_dir: str,
    csc_path:   str,
    debug:      bool = False
) -> tuple[str | None, str | None]:
    """
    Compile a launcher .exe for the given game.

    Parameters:
        game_name  — display name of the game (use for the .exe filename)
        launch_id  — the full prefixed ID, e.g. "MYSTORE:game_one_uri"
        output_dir — folder where the .exe should be written
        csc_path   — full path to csc.exe (the C# compiler)
        debug      — if True, show the compiler console window

    Returns:
        (exe_filename, None)     on success
        (None, error_string)     on failure
    """
    ...
```

**If you do not implement `create_exe`**, the app automatically uses a generic shell-execute launcher that does:
```csharp
Process.Start(new ProcessStartInfo {
    FileName = "your_uri_here",
    UseShellExecute = true
});
```
This is sufficient for any game that can be launched via a URI protocol like `battlenet://`, `goggalaxy://`, `uplay://`, etc.

---

## Full example — Battle.net plugin

This example adds Battle.net import support. Because `battlenet://` URIs work with shell execute, no `create_exe` is needed.

**plugin.json**
```json
{
  "name":        "Battle.net",
  "version":     "1.0.0",
  "author":      "yourname",
  "description": "Imports installed Battle.net games",
  "entry":       "battlenet.py"
}
```

**battlenet.py**
```python
import os
import json

PREFIXES = ["BNET"]

# Battle.net game URIs — add more as needed
KNOWN_GAMES = {
    "WTCG":   "Hearthstone",
    "Pro":    "Overwatch 2",
    "D3":     "Diablo III",
    "FENRIS": "Diablo IV",
    "W3":     "Warcraft III",
    "OSI":    "Diablo II: Resurrected",
    "FORE":   "Diablo Immortal",
    "S1":     "StarCraft",
    "S2":     "StarCraft II",
}

def find_games():
    games = []
    for product_code, display_name in KNOWN_GAMES.items():
        uri = f"battlenet://{product_code}"
        games.append((display_name, f"BNET:{uri}"))
    return sorted(games, key=lambda x: x[0].lower())
```

When the user imports from this plugin, each game gets a row like:
```
Diablo IV  |  BNET:battlenet://FENRIS
```

At generate time, the app sees `BNET:`, looks up the Battle.net plugin in the prefix registry, finds no `create_exe`, and automatically compiles a shell-execute launcher for `battlenet://FENRIS`.

---

## Full example — GOG Galaxy plugin (with custom exe logic)

This example shows `create_exe` for a launcher that requires command-line arguments.

**plugin.json**
```json
{
  "name":        "GOG Galaxy",
  "version":     "1.0.0",
  "author":      "yourname",
  "description": "Imports installed GOG games",
  "entry":       "gog.py"
}
```

**gog.py**
```python
import os
import subprocess
import tempfile

PREFIXES = ["GOG"]

def find_games():
    # Simplified — in practice you'd scan GOG's database
    return [
        ("The Witcher 3", "GOG:1207664663"),
        ("Cyberpunk 2077", "GOG:1423049311"),
    ]

def create_exe(game_name, launch_id, output_dir, csc_path, debug=False):
    import os, subprocess, tempfile

    # Sanitise the exe name
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()")
    exe_name = "".join(c if c in keep else "_" for c in game_name).strip() + ".exe"
    exe_path = os.path.join(output_dir, exe_name)

    game_id = launch_id.split(":", 1)[1]  # strip "GOG:"

    # GOG Galaxy uses a command-line argument to launch games
    galaxy_path = r"C:\\Program Files (x86)\\GOG Galaxy\\GalaxyClient.exe"

    cs_source = f"""using System;
using System.Diagnostics;
class Launcher {{
    static void Main() {{
        try {{
            Process.Start(new ProcessStartInfo {{
                FileName = "{galaxy_path}",
                Arguments = "/gameId={game_id} /command=runGame",
                UseShellExecute = true
            }});
        }} catch (Exception ex) {{ Console.Error.WriteLine(ex.Message); }}
    }}
}}
"""
    cs_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".cs", delete=False,
                                         mode="w", encoding="utf-8") as f:
            f.write(cs_source)
            cs_file = f.name

        flags = subprocess.CREATE_NO_WINDOW if not debug else 0
        result = subprocess.run(
            [csc_path, f"/out:{exe_path}", "/target:winexe", "/nologo", cs_file],
            capture_output=not debug, text=True,
            creationflags=flags, timeout=60)

        if result.returncode != 0:
            return None, result.stderr.strip() or "Compilation failed."
        if not os.path.isfile(exe_path):
            return None, "Compiler reported success but .exe was not created."
        return exe_name, None

    except Exception as e:
        return None, str(e)
    finally:
        if cs_file:
            try: os.unlink(cs_file)
            except OSError: pass
```

---

## Installing your plugin

1. Create your plugin folder with `plugin.json` and your `.py` file
2. Open Omni Game Linker
3. Go to **Settings → Plugin Configuration**
4. Set the **Plugin Directory** to the folder *containing* your plugin folder
5. Click **Apply & Reload Plugins**

Your plugin will appear in the **⬇ Import Games...** menu immediately.

---

## Debugging

Enable **Debug Mode** in Settings → Appearance & Behavior to see compiler output when generating `.exe` files. Plugin load errors are always shown in the main log panel on startup.

If your `find_games()` raises an exception, the error is caught and logged — the app will not crash.

---

## Tips

- Keep `find_games()` fast — it runs when the user clicks the menu item. If you need to scan the filesystem or call an API, it runs on a background thread so the UI stays responsive, but the user will see a loading state until it returns
- Return an empty list rather than raising if the store isn't installed — the app will show a "No games found" message
- Use `PREFIXES` even if you don't implement `create_exe` — it documents which IDs belong to your plugin and prevents conflicts with other plugins
- Test with Debug Mode on so you can see exactly what the C# compiler outputs if something goes wrong
