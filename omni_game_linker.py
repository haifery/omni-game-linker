import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import subprocess
import tempfile
import threading
import queue
import sys
import traceback
import json
import importlib.util
from PIL import Image

# Hide the console window when running on Windows.
import ctypes
if sys.platform == "win32":
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

APP_VERSION = "1.2.0"
APP_TITLE   = "Omni Game Linker"

# ---------------------------------------------------------------------------
# Appearance
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FONT_MAIN  = ("Segoe UI", 13)
FONT_BOLD  = ("Segoe UI", 13, "bold")
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_MONO  = ("Consolas", 12)
FONT_SMALL = ("Segoe UI", 11)


class Palette:
    """Global colours. Call set_accent() to update at runtime."""
    SUCCESS = "#28a745"
    ERROR   = "#d93025"
    MUTED   = "#8a8a9a"
    PANEL   = "#2b2b36"

    ACCENT       = "#e94560"
    ACCENT_HOVER = "#c73652"

    ACCENT_PRESETS = {
        "Red":    "#e94560",
        "Blue":   "#0078d4",
        "Green":  "#4caf80",
        "Purple": "#9b59b6",
        "Orange": "#e67e22",
    }

    @classmethod
    def set_accent(cls, hex_color: str):
        cls.ACCENT = hex_color
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        cls.ACCENT_HOVER = "#{:02x}{:02x}{:02x}".format(
            int(r * 0.85), int(g * 0.85), int(b * 0.85))


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

def _settings_path() -> str:
    base = os.path.expandvars(r"%APPDATA%") if sys.platform == "win32" else os.path.expanduser("~")
    folder = os.path.join(base, "OmniGameLinker")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")

def load_settings() -> dict:
    defaults = {
        "accent":         "Red",
        "debug":          False,
        "output_dir":     "",
        "plugin_dir":     "",
        "update_prompt":  True,   # show update prompt on startup
        "pending_update": "",     # path to a downloaded installer waiting to run
    }
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        defaults.update({k: v for k, v in saved.items() if k in defaults})
    except (OSError, json.JSONDecodeError):
        pass
    return defaults

def save_settings(settings: dict):
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Update system
# ---------------------------------------------------------------------------

GITHUB_REPO  = "haifery/omni-game-linker"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_DIR   = os.path.join(
    os.path.expandvars(r"%APPDATA%") if sys.platform == "win32"
    else os.path.expanduser("~"),
    "OmniGameLinker", "update")


def _version_tuple(v: str) -> tuple:
    """Convert 'v1.2.0' or '1.2.0' to (1, 2, 0) for comparison."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def check_for_updates() -> tuple | None:
    """
    Check GitHub releases API for a newer version.
    Returns (latest_version_str, asset_download_url) or None.
    Never raises.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": f"OmniGameLinker/{APP_VERSION}",
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            return None
        if _version_tuple(latest_tag) <= _version_tuple(APP_VERSION):
            return None

        # Find the Setup .exe asset
        download_url = RELEASES_URL
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".exe") and "Setup" in name:
                download_url = asset.get("browser_download_url")
                break

        return latest_tag, download_url
    except Exception:
        return None


def download_update(url: str, progress_callback=None) -> str | None:
    """
    Download installer to UPDATE_DIR.
    progress_callback(bytes_done, total_bytes) called each chunk.
    Returns local path on success, None on failure. Never raises.
    """
    try:
        import urllib.request
        os.makedirs(UPDATE_DIR, exist_ok=True)
        filename = url.split("/")[-1] or "OmniGameLinker_update.exe"
        dest     = os.path.join(UPDATE_DIR, filename)
        req = urllib.request.Request(
            url, headers={"User-Agent": f"OmniGameLinker/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total      = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
        return dest
    except Exception:
        # Clean up partial file if it exists
        try:
            dest_path = os.path.join(UPDATE_DIR,
                url.split("/")[-1] or "OmniGameLinker_update.exe")
            if os.path.isfile(dest_path):
                os.unlink(dest_path)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------

class PluginInfo:
    def __init__(self, name: str, version: str, author: str, description: str,
                 find_games_fn, create_exe_fn=None, prefixes: list = None):
        self.name        = name
        self.version     = version
        self.author      = author
        self.description = description
        self.prefixes    = prefixes or []
        self._find_games = find_games_fn
        self._create_exe = create_exe_fn

    def find_games(self) -> list:
        try:
            result = self._find_games()
            if isinstance(result, list):
                return result
        except Exception:
            pass
        return []

    def create_exe(self, game_name: str, launch_id: str, output_dir: str,
                   csc_path: str, debug: bool = False):
        if self._create_exe is None:
            return None, "no_impl"
        try:
            result = self._create_exe(game_name, launch_id, output_dir, csc_path, debug)
            if isinstance(result, (tuple, list)) and len(result) == 2:
                return result[0], result[1]
            return None, "Plugin create_exe() returned an unexpected value."
        except Exception as e:
            return None, f"Plugin create_exe() raised: {e}"


def load_plugins(plugin_dir: str) -> tuple:
    plugins, errors = [], []
    if not plugin_dir or not os.path.isdir(plugin_dir):
        return plugins, errors

    try:
        entries = os.listdir(plugin_dir)
    except OSError as e:
        return plugins, [f"Could not list plugin directory: {e}"]

    for entry in sorted(entries):
        plugin_folder = os.path.join(plugin_dir, entry)
        meta_path     = os.path.join(plugin_folder, "plugin.json")
        if not os.path.isdir(plugin_folder) or not os.path.isfile(meta_path):
            continue

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"[{entry}] Could not read plugin.json: {e}")
            continue

        name        = meta.get("name", entry)
        version     = meta.get("version", "?")
        author      = meta.get("author", "Unknown")
        description = meta.get("description", "")
        entry_file  = meta.get("entry", "")

        if not entry_file:
            errors.append(f"[{name}] plugin.json missing 'entry' field.")
            continue

        py_path = os.path.join(plugin_folder, entry_file)
        if not os.path.isfile(py_path):
            errors.append(f"[{name}] Entry file not found: {entry_file}")
            continue

        try:
            spec   = importlib.util.spec_from_file_location(f"plugin_{entry}", py_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            errors.append(f"[{name}] Failed to import {entry_file}: {e}")
            continue

        if not hasattr(module, "find_games") or not callable(module.find_games):
            errors.append(f"[{name}] Missing required find_games() function.")
            continue

        create_exe_fn = getattr(module, "create_exe", None)
        if create_exe_fn is not None and not callable(create_exe_fn):
            errors.append(f"[{name}] create_exe is not callable — ignoring it.")
            create_exe_fn = None

        raw_prefixes = getattr(module, "PREFIXES", [])
        if not isinstance(raw_prefixes, (list, tuple)):
            raw_prefixes = []
        prefixes = [str(p).upper().rstrip(":") for p in raw_prefixes if str(p).strip()]

        plugins.append(PluginInfo(name, version, author, description,
                                  module.find_games, create_exe_fn, prefixes))

    return plugins, errors


# ---------------------------------------------------------------------------
# Find Launchers & Games logic
# ---------------------------------------------------------------------------

def find_csc() -> str | None:
    candidates = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework64\v3.5\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v3.5\csc.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def sanitize_filename(name: str) -> str:
    keep   = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()")
    result = "".join(c if c in keep else "_" for c in name).strip()
    if not result:
        raise ValueError(f"Name '{name}' produced an empty filename after sanitization.")
    return result


def parse_shortcuts_vdf(path: str) -> list:
    import struct
    if not os.path.isfile(path):
        raise FileNotFoundError(f"shortcuts.vdf not found: {path}")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise OSError(f"Could not read shortcuts.vdf: {e}") from e
    if not data:
        raise ValueError("shortcuts.vdf is empty.")

    def read_string(pos):
        try:
            end = data.index(b"\x00", pos)
        except ValueError:
            raise ValueError(f"Malformed VDF: no null terminator at position {pos}.")
        return data[pos:end].decode("utf-8", errors="replace"), end + 1

    shortcuts, i, current = [], 0, {}
    try:
        while i < len(data):
            type_byte = data[i]
            i += 1
            if type_byte == 0x08:
                if "appname" in current and "appid" in current:
                    uid     = current["appid"] & 0xFFFFFFFF
                    game_id = (uid << 32) | 0x02000000
                    shortcuts.append((current["appname"], str(game_id)))
                current = {}
                continue
            if type_byte == 0x00:
                _, i = read_string(i)
            elif type_byte == 0x01:
                key, i = read_string(i)
                val, i = read_string(i)
                if key.lower() == "appname":
                    current["appname"] = val
            elif type_byte == 0x02:
                key, i = read_string(i)
                val     = struct.unpack_from("<i", data, i)[0]
                i      += 4
                if key.lower() == "appid":
                    current["appid"] = val
            elif type_byte == 0x03:
                _, i = read_string(i)
                i   += 4
            elif type_byte == 0x04:
                _, i = read_string(i)
                i   += 8
            else:
                i += 1
    except (ValueError, struct.error) as e:
        raise ValueError(f"VDF parse error at byte {i}: {e}") from e
    return shortcuts


def find_steam_shortcuts() -> list:
    steam_roots = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
    ]
    results, seen = [], set()
    for root in steam_roots:
        userdata = os.path.join(root, "userdata")
        if not os.path.isdir(userdata):
            continue
        try:
            user_ids = os.listdir(userdata)
        except OSError:
            continue
        for uid in user_ids:
            vdf = os.path.join(userdata, uid, "config", "shortcuts.vdf")
            if os.path.isfile(vdf) and vdf not in seen:
                seen.add(vdf)
                results.append((f"Steam user {uid}", vdf))
    return results


def find_installed_steam_games() -> list:
    steam_roots = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
    ]
    games, seen_ids = [], set()

    def parse_acf(path):
        name, appid = None, None
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('"name"'):
                        parts = line.split('"')
                        if len(parts) >= 4:
                            name = parts[3]
                    elif line.startswith('"appid"'):
                        parts = line.split('"')
                        if len(parts) >= 4:
                            appid = parts[3]
        except OSError:
            pass
        return name, appid

    def scan_library(steamapps_path):
        if not os.path.isdir(steamapps_path):
            return
        try:
            files = os.listdir(steamapps_path)
        except OSError:
            return
        for fname in files:
            if fname.startswith("appmanifest_") and fname.endswith(".acf"):
                name, appid = parse_acf(os.path.join(steamapps_path, fname))
                if name and appid and appid not in seen_ids:
                    seen_ids.add(appid)
                    games.append((name, appid))

    for steam_root in steam_roots:
        if not os.path.isdir(steam_root):
            continue
        scan_library(os.path.join(steam_root, "steamapps"))
        vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                with open(vdf, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if '"path"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4:
                                scan_library(os.path.join(parts[3], "steamapps"))
            except OSError:
                pass
    return sorted(games, key=lambda x: x[0].lower())


def find_prism_launcher() -> str | None:
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\PrismLauncher\prismlauncher.exe"),
        os.path.expandvars(r"%APPDATA%\PrismLauncher\prismlauncher.exe"),
        r"C:\Program Files\PrismLauncher\prismlauncher.exe",
        r"C:\Program Files (x86)\PrismLauncher\prismlauncher.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    try:
        result = subprocess.run(
            ["where", "prismlauncher"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode == 0:
            found = result.stdout.strip().splitlines()[0]
            if os.path.isfile(found):
                return found
    except OSError:
        pass
    return None


def find_prism_instances() -> list:
    prism_exe     = find_prism_launcher()
    instance_dirs = []
    default = os.path.expandvars(r"%APPDATA%\PrismLauncher\instances")
    if os.path.isdir(default):
        instance_dirs.append(default)

    cfg_path = os.path.expandvars(r"%APPDATA%\PrismLauncher\prismlauncher.cfg")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("InstanceDir="):
                        custom = line.split("=", 1)[1].strip()
                        if os.path.isdir(custom) and custom not in instance_dirs:
                            instance_dirs.append(custom)
        except OSError:
            pass

    instances, seen = [], set()
    for inst_dir in instance_dirs:
        try:
            entries = os.listdir(inst_dir)
        except OSError:
            continue
        for entry in sorted(entries):
            full = os.path.join(inst_dir, entry)
            cfg  = os.path.join(inst_dir, entry, "instance.cfg")
            if not os.path.isfile(cfg) or full in seen:
                continue
            seen.add(full)
            name = entry
            try:
                with open(cfg, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip().startswith("name="):
                            name = line.split("=", 1)[1].strip()
                            break
            except OSError:
                pass
            instances.append((name, entry, prism_exe))
    return instances


def find_epic_games() -> list:
    import json as _json
    manifests_dir = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    games         = []
    if not os.path.isdir(manifests_dir):
        return games
    try:
        files = os.listdir(manifests_dir)
    except OSError:
        return games

    for fname in files:
        if not fname.endswith(".item"):
            continue
        try:
            with open(os.path.join(manifests_dir, fname), "r",
                      encoding="utf-8", errors="replace") as f:
                data = _json.load(f)
        except (OSError, _json.JSONDecodeError):
            continue
        if not data.get("LaunchExecutable"):
            continue
        name      = data.get("DisplayName") or data.get("AppName", fname)
        namespace = data.get("CatalogNamespace", "")
        item_id   = data.get("CatalogItemId", "")
        app_name  = data.get("AppName", "")
        if not (namespace and item_id and app_name):
            continue
        uri = (f"com.epicgames.launcher://apps/"
               f"{namespace}%3A{item_id}%3A{app_name}?action=launch&silent=true")
        games.append((name, uri))
    return sorted(games, key=lambda x: x[0].lower())


def find_xbox_games() -> list:
    if sys.platform != "win32":
        return []
    import xml.etree.ElementTree as ET
    windowsapps = r"C:\Program Files\WindowsApps"
    games, seen_titles = [], set()
    skip_prefixes = (
        "Microsoft.NET", "Microsoft.VCLibs", "Microsoft.UI", "Microsoft.Windows",
        "Microsoft.Xbox", "Microsoft.Gaming", "Microsoft.DirectX",
        "Microsoft.Advertising", "Microsoft.Services", "Windows.",
        "Microsoft.StorePurchaseApp", "Microsoft.GamingApp",
        "Microsoft.XboxGameOverlay", "Microsoft.XboxGamingOverlay",
        "Microsoft.XboxIdentityProvider", "Microsoft.DesktopAppInstaller",
        "Microsoft.MicrosoftEdge", "Microsoft.OneDrive",
    )

    def _extract_from_manifest(manifest_path, pkg_name_hint=""):
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            ns   = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""

            def tag(t):
                return f"{{{ns}}}{t}" if ns else t

            identity = root.find(tag("Identity"))
            if identity is None:
                return None, None
            pkg_name = identity.get("Name", pkg_name_hint)
            if any(pkg_name.startswith(p) for p in skip_prefixes):
                return None, None

            display_name = pkg_name
            props = root.find(tag("Properties"))
            if props is not None:
                dn = props.find(tag("DisplayName"))
                if dn is not None and dn.text and not dn.text.startswith("ms-resource:"):
                    display_name = dn.text.strip()

            ms_xbl_uri = None
            for elem in root.iter():
                local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if local == "Protocol":
                    name_attr = elem.get("Name", "")
                    if name_attr.startswith("ms-xbl-"):
                        ms_xbl_uri = name_attr if name_attr.endswith("://") else name_attr + "://"
                        break
            return display_name, ms_xbl_uri
        except (ET.ParseError, OSError, PermissionError):
            return None, None

    try:
        entries = os.listdir(windowsapps)
    except PermissionError:
        entries = []

    for entry in entries:
        if any(entry.startswith(p) for p in skip_prefixes):
            continue
        manifest = os.path.join(windowsapps, entry, "AppxManifest.xml")
        if not os.path.isfile(manifest):
            continue
        display_name, ms_xbl_uri = _extract_from_manifest(manifest)
        if ms_xbl_uri and ms_xbl_uri not in seen_titles:
            seen_titles.add(ms_xbl_uri)
            games.append((display_name, ms_xbl_uri))

    if not games:
        try:
            flags  = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-AppxPackage | Select-Object Name,InstallLocation | ConvertTo-Json -Compress"],
                capture_output=True, text=True, creationflags=flags, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                packages = json.loads(result.stdout.strip())
                if isinstance(packages, dict):
                    packages = [packages]
                for pkg in packages:
                    pkg_name    = pkg.get("Name", "")
                    install_loc = pkg.get("InstallLocation", "")
                    if not install_loc or any(pkg_name.startswith(p) for p in skip_prefixes):
                        continue
                    manifest = os.path.join(install_loc, "AppxManifest.xml")
                    if not os.path.isfile(manifest):
                        continue
                    display_name, ms_xbl_uri = _extract_from_manifest(manifest, pkg_name)
                    if ms_xbl_uri and ms_xbl_uri not in seen_titles:
                        seen_titles.add(ms_xbl_uri)
                        games.append((display_name, ms_xbl_uri))
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    return sorted(games, key=lambda x: x[0].lower())


# ---------------------------------------------------------------------------
# Exe compilation
# ---------------------------------------------------------------------------

def _compile_csharp(cs_source: str, exe_path: str, csc_path: str,
                    debug: bool = False) -> str | None:
    cs_file = None
    try:
        try:
            with tempfile.NamedTemporaryFile(suffix=".cs", delete=False,
                                             mode="w", encoding="utf-8") as f:
                f.write(cs_source)
                cs_file = f.name
        except OSError as e:
            return f"Could not write temp .cs file: {e}"

        flags = 0 if debug else (subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            result = subprocess.run(
                [csc_path, f"/out:{exe_path}", "/target:winexe", "/nologo", cs_file],
                capture_output=not debug, text=True, creationflags=flags, timeout=60)
        except subprocess.TimeoutExpired:
            return "csc.exe timed out after 60 seconds."
        except OSError as e:
            return f"Could not launch csc.exe: {e}"

        if result.returncode != 0:
            return (result.stderr.strip() if result.stderr else "") or "Compilation failed (no output)."
        if not os.path.isfile(exe_path):
            return "Compilation reported success but .exe was not created."
        return None
    except Exception as e:
        return f"Unexpected error during compilation: {e}"
    finally:
        if cs_file:
            try:
                os.unlink(cs_file)
            except OSError:
                pass


def _cs_launcher(uri: str) -> str:
    """Return a minimal C# winexe source that shell-executes the given URI."""
    return (
        "using System; using System.Diagnostics;\n"
        "class Launcher { static void Main() { try { "
        f'Process.Start(new ProcessStartInfo {{ FileName = "{uri}", '
        "UseShellExecute = true }); } "
        "catch (Exception ex) { Console.Error.WriteLine(ex.Message); } } }"
    )


def create_exe(game_name, steam_id, output_dir, csc_path, debug=False):
    try:
        exe_name = sanitize_filename(game_name) + ".exe"
    except ValueError as e:
        return None, str(e)
    err = _compile_csharp(
        _cs_launcher(f"steam://rungameid/{steam_id}"),
        os.path.join(output_dir, exe_name), csc_path, debug)
    return (None, err) if err else (exe_name, None)


def create_prism_exe(instance_name, instance_id, prism_exe_path,
                     output_dir, csc_path, debug=False):
    try:
        exe_name = sanitize_filename(instance_name) + ".exe"
    except ValueError as e:
        return None, str(e)
    prism_escaped    = prism_exe_path.replace("\\", "\\\\")
    instance_escaped = instance_id.replace('"', '\\"')
    cs = (
        "using System; using System.Diagnostics;\n"
        "class Launcher { static void Main() { try { "
        f'Process.Start(new ProcessStartInfo {{ FileName = "{prism_escaped}", '
        f'Arguments = "--launch \\"{instance_escaped}\\"", '
        "UseShellExecute = true }); } "
        "catch (Exception ex) { Console.Error.WriteLine(ex.Message); } } }"
    )
    err = _compile_csharp(cs, os.path.join(output_dir, exe_name), csc_path, debug)
    return (None, err) if err else (exe_name, None)


def create_epic_exe(game_name, launch_uri, output_dir, csc_path, debug=False):
    try:
        exe_name = sanitize_filename(game_name) + ".exe"
    except ValueError as e:
        return None, str(e)
    err = _compile_csharp(
        _cs_launcher(launch_uri),
        os.path.join(output_dir, exe_name), csc_path, debug)
    return (None, err) if err else (exe_name, None)


def create_xbox_exe(game_name, ms_xbl_uri, output_dir, csc_path, debug=False):
    try:
        exe_name = sanitize_filename(game_name) + ".exe"
    except ValueError as e:
        return None, str(e)
    err = _compile_csharp(
        _cs_launcher(ms_xbl_uri),
        os.path.join(output_dir, exe_name), csc_path, debug)
    return (None, err) if err else (exe_name, None)


def create_generic_uri_exe(game_name: str, uri: str, output_dir: str,
                           csc_path: str, debug: bool = False):
    try:
        exe_name = sanitize_filename(game_name) + ".exe"
    except ValueError as e:
        return None, str(e)
    uri_escaped = uri.replace("\\", "\\\\").replace('"', '\\"')
    err = _compile_csharp(
        _cs_launcher(uri_escaped),
        os.path.join(output_dir, exe_name), csc_path, debug)
    return (None, err) if err else (exe_name, None)


# ---------------------------------------------------------------------------
# Checklist Import Dialog
# ---------------------------------------------------------------------------

class ChecklistImportDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, heading: str, items: list,
                 show_subtitle: bool = True):
        super().__init__(parent)
        self.selected  = []
        self._items    = items
        self._show_sub = show_subtitle

        self.title(title)
        self.geometry("540x460")
        self.resizable(True, True)
        self.minsize(400, 300)
        self.transient(parent)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text=heading, font=FONT_BOLD).pack(side="left")
        ctk.CTkLabel(head, text=f"({len(items)} found)",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(side="left", padx=10)

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkButton(ctrl, text="Select All",  command=self._select_all,
                      width=90).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ctrl, text="Select None", command=self._select_none,
                      width=90, fg_color="transparent",
                      border_width=1).pack(side="left")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_filter())
        ctk.CTkEntry(ctrl, textvariable=self._search_var,
                     placeholder_text="Search…", width=180).pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=20, pady=4)

        self._vars        = []
        self._row_widgets = []
        self._build_rows(items)

        self._empty_label = ctk.CTkLabel(
            self._scroll, text="No results match your search.",
            text_color=Palette.MUTED, font=FONT_MAIN)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(foot, text="Import Selected", command=self._confirm, width=130,
                      fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                      font=FONT_BOLD).pack(side="left")
        ctk.CTkButton(foot, text="Cancel", command=self.destroy, width=90,
                      fg_color="transparent", border_width=1).pack(side="left", padx=10)

        self._center(parent)
        self.wait_window()

    def _build_rows(self, items):
        self._vars.clear()
        self._row_widgets.clear()
        for display_name, id_value in items:
            var = tk.BooleanVar(value=False)
            self._vars.append((var, display_name, id_value))
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(row, text=display_name, variable=var,
                            font=FONT_MAIN).pack(side="left", padx=(0, 10))
            if self._show_sub and id_value:
                ctk.CTkLabel(row, text=id_value, text_color=Palette.MUTED,
                             font=FONT_MONO).pack(side="right")
            self._row_widgets.append((row, display_name.lower()))

    def _refresh_filter(self):
        query   = self._search_var.get().lower().strip()
        visible = 0
        for (row, name_lower), _ in zip(self._row_widgets, self._vars):
            show = not query or query in name_lower
            if show:
                row.pack(fill="x", pady=2)
                visible += 1
            else:
                row.pack_forget()
        if visible == 0:
            self._empty_label.pack(pady=20)
        else:
            self._empty_label.pack_forget()

    def _select_all(self):
        for var, _, __ in self._vars:
            var.set(True)

    def _select_none(self):
        for var, _, __ in self._vars:
            var.set(False)

    def _confirm(self):
        self.selected = [(name, id_val) for var, name, id_val in self._vars if var.get()]
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + pw // 2 - w // 2}+{py + ph // 2 - h // 2}")


# ---------------------------------------------------------------------------
# Steam import dialog
# ---------------------------------------------------------------------------

class SteamImportDialog(ctk.CTkToplevel):
    def __init__(self, parent, shortcuts: list, all_games: list):
        super().__init__(parent)
        self.selected    = []
        self._shortcuts  = shortcuts
        self._all_games  = all_games
        self._show_all   = tk.BooleanVar(value=False)
        self._search_var = tk.StringVar()

        self.title("Import from Steam")
        self.geometry("540x480")
        self.resizable(True, True)
        self.minsize(400, 320)
        self.transient(parent)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        self._title_label = ctk.CTkLabel(head, text="", font=FONT_BOLD)
        self._title_label.pack(side="left")
        self._count_label = ctk.CTkLabel(head, text="",
                                          text_color=Palette.MUTED, font=FONT_MAIN)
        self._count_label.pack(side="left", padx=10)

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=(0, 6))
        ctk.CTkButton(ctrl, text="Select All",  command=self._select_all,
                      width=90).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ctrl, text="Select None", command=self._select_none,
                      width=90, fg_color="transparent",
                      border_width=1).pack(side="left")
        ctk.CTkSwitch(ctrl, text="Show all installed", variable=self._show_all,
                      command=self._rebuild_list,
                      font=FONT_MAIN).pack(side="right")

        self._search_var.trace_add("write", lambda *_: self._refresh_filter())
        ctk.CTkEntry(ctrl, textvariable=self._search_var,
                     placeholder_text="Search…",
                     width=160).pack(side="right", padx=(0, 10))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=20, pady=4)

        self._vars, self._row_widgets = [], []
        self._empty_label = ctk.CTkLabel(
            self._scroll, text="No results match your search.",
            text_color=Palette.MUTED, font=FONT_MAIN)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(foot, text="Import Selected", command=self._confirm, width=130,
                      fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                      font=FONT_BOLD).pack(side="left")
        ctk.CTkButton(foot, text="Cancel", command=self.destroy, width=90,
                      fg_color="transparent", border_width=1).pack(side="left", padx=10)

        self._rebuild_list()
        self._center(parent)
        self.wait_window()

    def _rebuild_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._vars.clear()
        self._row_widgets.clear()

        showing_all = self._show_all.get()
        source      = self._all_games if showing_all else self._shortcuts
        self._title_label.configure(
            text="All installed Steam games" if showing_all else "Added shortcuts")
        self._count_label.configure(text=f"({len(source)} found)")

        for name, sid in source:
            var = tk.BooleanVar(value=False)
            self._vars.append((var, name, sid))
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(row, text=name, variable=var,
                            font=FONT_MAIN).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(row, text=sid, text_color=Palette.MUTED,
                         font=FONT_MONO).pack(side="right")
            self._row_widgets.append((row, name.lower()))

        self._empty_label = ctk.CTkLabel(
            self._scroll, text="No results match your search.",
            text_color=Palette.MUTED, font=FONT_MAIN)
        self._refresh_filter()

    def _refresh_filter(self):
        query   = self._search_var.get().lower().strip()
        visible = 0
        for (row, name_lower), _ in zip(self._row_widgets, self._vars):
            show = not query or query in name_lower
            if show:
                row.pack(fill="x", pady=2)
                visible += 1
            else:
                row.pack_forget()
        if visible == 0:
            self._empty_label.pack(pady=20)
        else:
            self._empty_label.pack_forget()

    def _select_all(self):
        for var, *_ in self._vars:
            var.set(True)

    def _select_none(self):
        for var, *_ in self._vars:
            var.set(False)

    def _confirm(self):
        self.selected = [(name, sid) for var, name, sid in self._vars if var.get()]
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + pw // 2 - w // 2}+{py + ph // 2 - h // 2}")


# ---------------------------------------------------------------------------
# Folder name confirmation dialog
# ---------------------------------------------------------------------------

class FolderNameDialog(ctk.CTkToplevel):
    def __init__(self, parent, game_name: str, index: int, total: int):
        super().__init__(parent)
        self.result       = None
        self.cancelled    = False
        self.auto_confirm = False

        self.title("Confirm Folder Name")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(pad, text=f"Game {index} of {total}",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(anchor="w")
        ctk.CTkLabel(pad, text="Folder name",
                     font=FONT_BOLD).pack(anchor="w", pady=(10, 4))

        try:
            default = sanitize_filename(game_name)
        except ValueError:
            default = "unnamed_game"

        self._var = tk.StringVar(value=default)
        entry = ctk.CTkEntry(pad, textvariable=self._var, width=320, font=FONT_MAIN)
        entry.pack(fill="x", pady=(0, 20))
        entry.select_range(0, "end")
        entry.focus_set()

        btn_frame = ctk.CTkFrame(pad, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="Confirm", command=self._confirm, width=90,
                      fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                      font=FONT_BOLD).pack(side="left")
        ctk.CTkButton(btn_frame, text="Auto-confirm All", command=self._confirm_all,
                      width=140, font=FONT_MAIN).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Skip", command=self._skip, width=70,
                      fg_color="transparent", border_width=1,
                      font=FONT_MAIN).pack(side="right")

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._skip())
        self._center(parent)
        self.wait_window()

    def _confirm(self):
        name = self._var.get().strip()
        if name:
            self.result = name
            self.destroy()

    def _confirm_all(self):
        name = self._var.get().strip()
        if name:
            self.result       = name
            self.auto_confirm = True
            self.destroy()

    def _skip(self):
        self.cancelled = True
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + pw // 2 - w // 2}+{py + ph // 2 - h // 2}")


# ---------------------------------------------------------------------------
# Row
# ---------------------------------------------------------------------------

class Row:
    def __init__(self, parent_frame, row_index: int, remove_callback):
        self.frame = ctk.CTkFrame(parent_frame, corner_radius=6)
        self.frame.pack(fill="x", pady=4)

        self.name_var = tk.StringVar()
        self.id_var   = tk.StringVar()

        self.num_label = ctk.CTkLabel(
            self.frame, text=str(row_index), width=30,
            text_color=Palette.MUTED, font=FONT_MAIN)
        self.num_label.pack(side="left", padx=(10, 5))

        ctk.CTkEntry(self.frame, textvariable=self.name_var,
                     placeholder_text="Game Name").pack(
            side="left", padx=5, pady=6, expand=True, fill="x")

        ctk.CTkEntry(self.frame, textvariable=self.id_var, width=300,
                     placeholder_text="Steam ID or Prefix:URI").pack(
            side="left", padx=5, pady=6)

        ctk.CTkButton(self.frame, text="✕", width=30,
                      command=lambda: remove_callback(self),
                      fg_color="transparent", text_color=Palette.MUTED,
                      hover_color=Palette.ERROR).pack(side="right", padx=(5, 10))

    def get(self) -> tuple:
        return self.name_var.get().strip(), self.id_var.get().strip()

    def destroy(self):
        self.frame.destroy()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1020x640")
        self.root.minsize(860, 500)

        # Set the window/taskbar icon
        try:
            _ico = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
            if os.path.isfile(_ico):
                self.root.iconbitmap(_ico)
        except Exception:
            pass

        self.rows      = []
        self.output_dir = tk.StringVar()
        self.log_queue  = queue.Queue()
        self._debug_mode = tk.BooleanVar(value=False)
        self._plugins: list[PluginInfo] = []
        self._plugin_prefix_registry: dict[str, PluginInfo] = {}

        self.root.report_callback_exception = self._handle_uncaught_exception

        self._settings = load_settings()
        accent_name    = self._settings.get("accent", "Red")
        accent_hex     = Palette.ACCENT_PRESETS.get(accent_name, Palette.ACCENT)
        Palette.set_accent(accent_hex)
        self._debug_mode.set(self._settings.get("debug", False))
        saved_dir = self._settings.get("output_dir", "")
        if saved_dir:
            self.output_dir.set(saved_dir)

        self._build_ui()
        self._add_row()
        self._process_log_queue()
        self._log("Application started.", "info")
        self._log(f"  Version {APP_VERSION}", "info")
        self._reload_plugins(silent=False)

        # Run any pending update that was downloaded on a previous session
        self.root.after(500, self._run_pending_update)
        # Silent startup update check
        if self._settings.get("update_prompt", True):
            self.root.after(2000, self._startup_update_check)

    # ── Exception handler ────────────────────────────────────────────────────

    def _handle_uncaught_exception(self, exc_type, exc_value, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self._log(f"⚠  Uncaught exception:\n{tb}", "err")

    # ── Settings ─────────────────────────────────────────────────────────────

    def _save(self):
        self._settings["debug"]      = self._debug_mode.get()
        self._settings["output_dir"] = self.output_dir.get().strip()
        save_settings(self._settings)

    # ── Update system ─────────────────────────────────────────────────────────

    def _run_pending_update(self):
        """On startup, check if a downloaded installer is waiting to run."""
        pending = self._settings.get("pending_update", "").strip()
        if not pending or not os.path.isfile(pending):
            if pending:
                # File is gone — clear the stale entry
                self._settings["pending_update"] = ""
                self._save()
            return

        run = messagebox.askyesno(
            "Update ready",
            f"An update for Omni Game Linker is ready to install.\n\n"
            f"Would you like to install it now?\n\n"
            f"The app will close and the installer will run.",
            icon="info")

        if run:
            try:
                subprocess.Popen([pending, "/SILENT"])
                self._settings["pending_update"] = ""
                self._save()
                self.root.after(500, self.root.destroy)
            except Exception as e:
                messagebox.showerror("Update failed",
                    f"Could not launch the installer:\n{e}\n\n"
                    f"You can run it manually from:\n{pending}")
        else:
            # User declined — clear it so we don't ask again
            self._settings["pending_update"] = ""
            self._save()

    def _startup_update_check(self):
        """Silent background check — only shows UI if update is found."""
        def check():
            result = check_for_updates()
            if result:
                self.root.after(0, lambda: self._show_update_prompt(*result,
                                                                     silent=True))
        threading.Thread(target=check, daemon=True).start()

    def _manual_update_check(self, status_label=None):
        """Manual check triggered from Version dialog."""
        if status_label:
            status_label.configure(text="Checking…", text_color=Palette.MUTED)

        def check():
            result = check_for_updates()
            if result:
                self.root.after(0, lambda: self._show_update_prompt(*result,
                                                                     silent=False))
            else:
                def _no_update():
                    if status_label:
                        status_label.configure(
                            text="✓  You're up to date.", text_color=Palette.SUCCESS)
                    else:
                        messagebox.showinfo("Up to date",
                            f"You're running the latest version ({APP_VERSION}).")
                self.root.after(0, _no_update)

        threading.Thread(target=check, daemon=True).start()

    def _show_update_prompt(self, latest: str, download_url: str,
                            silent: bool = False):
        """Show the update available dialog with all three options."""
        win = ctk.CTkToplevel(self.root)
        win.title("Update Available")
        win.geometry("440x320")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        ctk.CTkLabel(win, text="Update Available", font=FONT_TITLE).pack(
            anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(win,
                     text=f"Version {latest} is available.\nYou are running {APP_VERSION}.",
                     font=FONT_MAIN, text_color=Palette.MUTED).pack(
            anchor="w", padx=24, pady=(0, 20))

        # Progress bar (hidden until download starts)
        progress_frame = ctk.CTkFrame(win, fg_color="transparent")
        progress_frame.pack(fill="x", padx=24, pady=(0, 8))
        progress_bar   = ctk.CTkProgressBar(progress_frame)
        progress_label = ctk.CTkLabel(progress_frame, text="", font=FONT_SMALL,
                                      text_color=Palette.MUTED)

        def _show_progress():
            progress_bar.set(0)
            progress_bar.pack(fill="x", pady=(0, 4))
            progress_label.pack(anchor="w")
            for btn in (btn_now, btn_next, btn_releases, btn_skip):
                btn.configure(state="disabled")

        def _update_progress(done, total):
            if total > 0:
                pct = done / total
                self.root.after(0, lambda p=pct, d=done, t=total: (
                    progress_bar.set(p),
                    progress_label.configure(
                        text=f"Downloading… {done//1024//1024:.1f} MB / "
                             f"{total//1024//1024:.1f} MB ({p*100:.0f}%)")))
            else:
                self.root.after(0, lambda d=done: progress_label.configure(
                    text=f"Downloading… {d//1024//1024:.1f} MB"))

        def _on_download_fail():
            """Cancel update, report error, ask what to do next."""
            progress_bar.pack_forget()
            progress_label.pack_forget()
            for btn in (btn_now, btn_next, btn_releases, btn_skip):
                btn.configure(state="normal")
            choice = messagebox.askquestion(
                "Download failed",
                "The update download failed or was interrupted.\n\n"
                "Would you like to open the GitHub releases page to download manually?",
                icon="error",
                type=messagebox.YESNO)
            if choice == "yes":
                import webbrowser
                webbrowser.open(RELEASES_URL)
                win.destroy()

        def do_now():
            """Download then install immediately with /SILENT."""
            _show_progress()
            def run():
                path = download_update(download_url, _update_progress)
                if path:
                    self.root.after(0, lambda: _launch_now(path))
                else:
                    self.root.after(0, _on_download_fail)
            threading.Thread(target=run, daemon=True).start()

        def _launch_now(path):
            try:
                subprocess.Popen([path, "/SILENT"])
                win.destroy()
                self.root.after(500, self.root.destroy)
            except Exception as e:
                messagebox.showerror("Launch failed",
                    f"Could not start the installer:\n{e}")

        def do_next():
            """Download and save path — will run on next startup."""
            _show_progress()
            def run():
                path = download_update(download_url, _update_progress)
                if path:
                    def _save_pending():
                        self._settings["pending_update"] = path
                        self._save()
                        progress_label.configure(
                            text="✓  Downloaded. Will install on next launch.",
                            text_color=Palette.SUCCESS)
                        win.after(1500, win.destroy)
                    self.root.after(0, _save_pending)
                else:
                    self.root.after(0, _on_download_fail)
            threading.Thread(target=run, daemon=True).start()

        def do_releases():
            import webbrowser
            webbrowser.open(RELEASES_URL)
            win.destroy()

        def do_skip():
            if silent:
                self._settings["update_prompt"] = False
                self._save()
                self._log("  Update prompt disabled. Re-enable in Settings → Updates.", "info")
            win.destroy()

        btn_now = ctk.CTkButton(win, text="⚡ Update & Restart Now",
                                command=do_now, font=FONT_BOLD,
                                fg_color=Palette.ACCENT,
                                hover_color=Palette.ACCENT_HOVER)
        btn_now.pack(fill="x", padx=24, pady=(0, 8))

        btn_next = ctk.CTkButton(win, text="⬇ Download & Update on Next Launch",
                                 command=do_next, font=FONT_MAIN,
                                 fg_color="transparent", border_width=1,
                                 border_color=Palette.ACCENT,
                                 text_color=Palette.ACCENT)
        btn_next.pack(fill="x", padx=24, pady=(0, 8))

        btn_releases = ctk.CTkButton(win, text="🌐 Open Releases Page",
                                     command=do_releases, font=FONT_MAIN,
                                     fg_color="transparent", border_width=1)
        btn_releases.pack(fill="x", padx=24, pady=(0, 16))

        btn_skip = ctk.CTkButton(win,
                                 text="Don't ask again" if silent else "Close",
                                 command=do_skip, font=FONT_SMALL,
                                 fg_color="transparent",
                                 text_color=Palette.MUTED)
        btn_skip.pack(pady=(0, 12))

    # ── Plugin management ────────────────────────────────────────────────────

    def _reload_plugins(self, silent: bool = True):
        plugin_dir      = self._settings.get("plugin_dir", "").strip()
        plugins, errors = load_plugins(plugin_dir)
        self._plugins   = plugins

        self._plugin_prefix_registry = {}
        for plugin in plugins:
            for prefix in plugin.prefixes:
                if prefix in self._plugin_prefix_registry:
                    self._log(
                        f"  ⚠  Prefix conflict: '{prefix}' claimed by "
                        f"'{self._plugin_prefix_registry[prefix].name}' and "
                        f"'{plugin.name}'. '{plugin.name}' will be used.", "err")
                self._plugin_prefix_registry[prefix] = plugin

        if not silent:
            if plugin_dir:
                self._log(f"\n── Plugins (dir: {plugin_dir}) ──", "info")
            else:
                self._log("\n── Plugins ── (no plugin directory configured)", "info")

        for err in errors:
            self._log(f"  ⚠  Plugin error: {err}", "err")

        if plugins and not silent:
            for p in plugins:
                self._log(f"  ✓  Loaded: {p.name} v{p.version} by {p.author}", "ok")

    # ── Import from plugin ────────────────────────────────────────────────────

    def _import_from_plugin(self, plugin: PluginInfo):
        self._log(f"\n── Import from {plugin.name} ──", "info")
        self._log("  Scanning via plugin…", "info")

        def scan():
            try:
                games = plugin.find_games()
                self.root.after(0, lambda: self._on_plugin_scan_done(plugin, games))
            except Exception:
                msg = traceback.format_exc()
                self.root.after(0, lambda m=msg: self._log(
                    f"⚠  Plugin '{plugin.name}' raised an error:\n    {m}", "err"))

        threading.Thread(target=scan, daemon=True).start()

    def _on_plugin_scan_done(self, plugin: PluginInfo, games: list):
        if not games:
            self._log(f"⚠  {plugin.name} returned no games.", "err")
            messagebox.showinfo("No games found",
                f"'{plugin.name}' did not return any games.\n\n"
                "Check the plugin configuration or your installation.")
            return

        self._log(f"  Found {len(games)} game(s) via {plugin.name}.", "info")
        dlg = ChecklistImportDialog(self.root, f"Import — {plugin.name}",
                                    plugin.name, games, show_subtitle=True)
        if not dlg.selected:
            self._log("  Import dialog closed with no selection.", "info")
            return

        self._consume_blank_row()
        for name, id_val in dlg.selected:
            try:
                row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
                row.name_var.set(name)
                row.id_var.set(id_val)
                self.rows.append(row)
                self._log(f"    + {name}", "ok")
            except Exception as e:
                self._log(f"⚠  Could not add row for '{name}': {e}", "err")
        self._repack_add_button()
        self._log(f"  Import complete — {len(dlg.selected)} row(s) added.", "ok")

    # ── Accent update ────────────────────────────────────────────────────────

    def _apply_accent(self):
        try:
            a, h = Palette.ACCENT, Palette.ACCENT_HOVER
            self.header_stripe.configure(fg_color=a)
            self.btn_browse.configure(fg_color=a, hover_color=h)
            self.btn_add_row.configure(fg_color=a, hover_color=h)
            self.btn_generate.configure(fg_color=a, hover_color=h)
            self.rows_frame.configure(scrollbar_button_color=a,
                                      scrollbar_button_hover_color=h)
            self.btn_import_menu.configure(border_color=a, text_color=a)
        except Exception as e:
            self._log(f"⚠  Accent update failed: {e}", "err")

    # ── UI build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.header_stripe = ctk.CTkFrame(self.root, fg_color=Palette.ACCENT,
                                          height=3, corner_radius=0)
        self.header_stripe.pack(fill="x")

        title_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        title_bar.pack(fill="x", padx=20, pady=(14, 8))

        # Try to load the app icon next to the title
        try:
            _icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", "icon_transparent.png")
            if os.path.isfile(_icon_path):
                _pil_img = Image.open(_icon_path).resize((28, 28), Image.LANCZOS)
                _ctk_img = ctk.CTkImage(light_image=_pil_img, dark_image=_pil_img,
                                        size=(28, 28))
                ctk.CTkLabel(title_bar, image=_ctk_img, text="").pack(
                    side="left", padx=(0, 8))
        except Exception:
            pass  # icon missing or PIL unavailable — just skip it

        ctk.CTkLabel(title_bar, text="Omni Game Linker",
                     font=FONT_TITLE).pack(side="left")
        ctk.CTkLabel(title_bar, text="universal launcher .exe builder",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(side="left", padx=14)
        self._menu_btn = ctk.CTkButton(
            title_bar, text="⋮", width=32, height=32,
            font=("Segoe UI", 18, "bold"),
            fg_color="transparent", hover_color=("gray80", "gray25"),
            text_color=("black", "white"), command=self._show_menu)
        self._menu_btn.pack(side="right")

        dir_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        dir_frame.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(dir_frame, text="Output directory:",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(
            side="left", padx=(0, 10))
        ctk.CTkEntry(dir_frame, textvariable=self.output_dir,
                     font=FONT_MAIN).pack(side="left", expand=True, fill="x")
        self.btn_browse = ctk.CTkButton(
            dir_frame, text="Browse", command=self._browse,
            width=80, fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER)
        self.btn_browse.pack(side="left", padx=(10, 0))
        self.output_dir.trace_add("write", lambda *_: self._save())

        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=(4, 4))

        col_header = ctk.CTkFrame(container, fg_color="transparent")
        col_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(col_header, text="#", width=30,
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(
            side="left", padx=(10, 5))
        ctk.CTkLabel(col_header, text="Game Name", anchor="w",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(
            side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(col_header, text="Launch ID / URI", width=300, anchor="w",
                     text_color=Palette.MUTED, font=FONT_MAIN).pack(
            side="left", padx=5)
        ctk.CTkLabel(col_header, text="", width=40).pack(side="left")

        self.rows_frame = ctk.CTkScrollableFrame(
            container, fg_color="transparent",
            scrollbar_button_color=Palette.ACCENT,
            scrollbar_button_hover_color=Palette.ACCENT_HOVER)
        self.rows_frame.pack(fill="both", expand=True)

        self.btn_add_row = ctk.CTkButton(
            self.rows_frame, text="+ Add Row", command=self._add_row, width=110,
            fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER)

        action_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        action_bar.pack(fill="x", padx=20, pady=(12, 8))

        self.btn_import_menu = ctk.CTkButton(
            action_bar, text="⬇ Import Games...",
            command=self._show_import_menu, width=160,
            fg_color="transparent", border_width=1,
            border_color=Palette.ACCENT, text_color=Palette.ACCENT,
            font=FONT_BOLD)
        self.btn_import_menu.pack(side="left", padx=(0, 15))

        self.btn_generate = ctk.CTkButton(
            action_bar, text="⚡ Generate All", command=self._start_generate,
            width=150, fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
            font=FONT_BOLD)
        self.btn_generate.pack(side="left")

        ctk.CTkButton(action_bar, text="Clear All", command=self._clear_all,
                      width=80, fg_color="transparent", text_color=Palette.MUTED,
                      hover_color=Palette.ERROR).pack(side="right")

        self.log = ctk.CTkTextbox(self.root, height=130, font=FONT_MONO,
                                   state="disabled")
        self.log.pack(fill="x", padx=20, pady=(2, 16))
        self.log.tag_config("ok",   foreground=Palette.SUCCESS)
        self.log.tag_config("err",  foreground=Palette.ERROR)
        self.log.tag_config("info", foreground=Palette.MUTED)

    # ── Menus ─────────────────────────────────────────────────────────────────

    def _show_import_menu(self):
        try:
            menu = tk.Menu(self.root, tearoff=0,
                           bg=Palette.PANEL, fg="white",
                           activebackground=Palette.ACCENT, activeforeground="white",
                           font=FONT_MAIN, bd=0, relief="flat", activeborderwidth=0)
            menu.add_command(label="  Steam Library",
                             command=self._import_from_steam)
            menu.add_command(label="  Epic Games",
                             command=self._import_from_epic)
            menu.add_command(label="  Xbox / PC Game Pass",
                             command=self._import_from_xbox)
            menu.add_command(label="  Prism Launcher",
                             command=self._import_from_prism)
            if self._plugins:
                menu.add_separator()
                for p in self._plugins:
                    menu.add_command(label=f"  {p.name}",
                                     command=lambda pl=p: self._import_from_plugin(pl))
            x = self.btn_import_menu.winfo_rootx()
            y = self.btn_import_menu.winfo_rooty() + self.btn_import_menu.winfo_height()
            menu.tk_popup(x, y)
        except Exception as e:
            self._log(f"⚠  Could not open import menu: {e}", "err")

    def _show_menu(self):
        try:
            menu = tk.Menu(self.root, tearoff=0,
                           bg=Palette.PANEL, fg="white",
                           activebackground=Palette.ACCENT, activeforeground="white",
                           font=FONT_MAIN, bd=0, relief="flat", activeborderwidth=0)
            menu.add_command(label="  Help",     command=self._open_help)
            menu.add_command(label="  Settings", command=self._open_settings)
            menu.add_separator()
            menu.add_command(label="  Version",  command=self._open_version)
            x = self._menu_btn.winfo_rootx()
            y = self._menu_btn.winfo_rooty() + self._menu_btn.winfo_height()
            menu.tk_popup(x, y)
        except Exception as e:
            self._log(f"⚠  Could not open menu: {e}", "err")

    def _open_help(self):
        try:
            win = ctk.CTkToplevel(self.root)
            win.title("Help")
            win.geometry("520x560")
            win.resizable(True, True)
            win.transient(self.root)
            win.grab_set()

            ctk.CTkLabel(win, text="How to use Omni Game Linker",
                         font=FONT_TITLE).pack(anchor="w", padx=24, pady=(20, 0))

            scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=24, pady=(10, 0))

            steps = [
                ("1. Add your games",
                 "Type a game name and its Launch ID into a row, or click "
                 "'⬇ Import Games...' to automatically pull installed games "
                 "from Steam, Epic, Xbox, Prism, or your custom plugins."),
                ("2. Launch IDs explained",
                 "Different platforms use different ID formats:\n"
                 "  • Steam:  numeric App ID  (e.g. 1091500)\n"
                 "  • Epic:   EPIC:<uri>\n"
                 "  • Xbox:   XBOX:ms-xbl-...://\n"
                 "  • Prism:  PRISM:<instance_id>|<path_to_exe>\n"
                 "  • Custom: any PREFIX:<uri>  (e.g. GOG:goggalaxy://...)"),
                ("3. Choose an output folder",
                 "Select the parent directory where shortcuts will be saved. "
                 "A dedicated subfolder is created for each game containing "
                 "its generated .exe. Your last used folder is remembered."),
                ("4. Generate",
                 "Click '⚡ Generate All'. You'll be prompted to confirm the "
                 "folder name for each game. Hit 'Auto-confirm All' to approve "
                 "the rest automatically."),
                ("5. Adding plugins",
                 "In Settings, select a Plugin Directory. A plugin is a folder "
                 "containing a plugin.json and a Python script that scrapes a "
                 "storefront. Valid plugins appear automatically in the "
                 "'Import Games...' menu."),
                ("6. Debug mode",
                 "Enable Debug Mode in Settings to show the C# compiler console "
                 "during generation — useful if a .exe fails to compile.\n\n"
                 "To eliminate the CMD flash on startup, launch with pythonw.exe "
                 "or build with PyInstaller --noconsole."),
            ]

            for title, body in steps:
                ctk.CTkLabel(scroll, text=title, font=FONT_BOLD,
                             anchor="w").pack(fill="x", pady=(14, 2))
                ctk.CTkLabel(scroll, text=body, font=FONT_MAIN, anchor="w",
                             justify="left", text_color=Palette.MUTED,
                             wraplength=440).pack(fill="x")

            ctk.CTkButton(win, text="Close", command=win.destroy, width=80,
                          fg_color=Palette.ACCENT,
                          hover_color=Palette.ACCENT_HOVER).pack(pady=(10, 18))
        except Exception as e:
            self._log(f"⚠  Could not open Help: {e}", "err")

    def _open_settings(self):
        try:
            win = ctk.CTkToplevel(self.root)
            win.title("Settings")
            win.geometry("460x580")
            win.resizable(False, True)
            win.minsize(460, 400)
            win.transient(self.root)
            win.grab_set()

            ctk.CTkLabel(win, text="Settings", font=FONT_TITLE).pack(
                anchor="w", padx=24, pady=(20, 0))

            pad = ctk.CTkScrollableFrame(win, fg_color="transparent")
            pad.pack(fill="both", expand=True, padx=24, pady=(8, 0))

            # ── Appearance card ──
            card_app = ctk.CTkFrame(pad, corner_radius=8)
            card_app.pack(fill="x", pady=(0, 16))
            ctk.CTkLabel(card_app, text="Appearance & Behavior",
                         font=FONT_BOLD).pack(anchor="w", padx=16, pady=(12, 4))

            current_name = next(
                (n for n, h in Palette.ACCENT_PRESETS.items()
                 if h.lower() == Palette.ACCENT.lower()), "Red")

            def apply_accent(label):
                try:
                    Palette.set_accent(Palette.ACCENT_PRESETS[label])
                    self._apply_accent()
                    self._settings["accent"] = label
                    self._save()
                    self._log(f"  Accent → {label} ({Palette.ACCENT}).", "info")
                except Exception as e:
                    self._log(f"⚠  Could not apply accent: {e}", "err")

            accent_var = tk.StringVar(value=current_name)
            ctk.CTkOptionMenu(card_app, variable=accent_var,
                              values=list(Palette.ACCENT_PRESETS.keys()),
                              command=apply_accent).pack(
                fill="x", padx=16, pady=(4, 12))

            def on_debug_toggle():
                try:
                    if sys.platform == "win32":
                        show = 1 if self._debug_mode.get() else 0
                        ctypes.windll.user32.ShowWindow(
                            ctypes.windll.kernel32.GetConsoleWindow(), show)
                    self._settings["debug"] = self._debug_mode.get()
                    self._save()
                    self._log(
                        f"  Debug mode "
                        f"{'enabled' if self._debug_mode.get() else 'disabled'}.",
                        "info")
                except Exception as e:
                    self._log(f"⚠  Debug toggle failed: {e}", "err")

            ctk.CTkCheckBox(card_app, text="Show compiler console during generation",
                            variable=self._debug_mode, command=on_debug_toggle,
                            font=FONT_MAIN).pack(anchor="w", padx=16, pady=(4, 2))
            ctk.CTkLabel(card_app,
                         text="Useful for diagnosing .exe compilation errors.",
                         font=FONT_SMALL, text_color=Palette.MUTED,
                         anchor="w").pack(fill="x", padx=16, pady=(0, 16))

            # ── Plugin card ──
            card_plug = ctk.CTkFrame(pad, corner_radius=8)
            card_plug.pack(fill="x", pady=(0, 16))
            ctk.CTkLabel(card_plug, text="Plugin Configuration",
                         font=FONT_BOLD).pack(anchor="w", padx=16, pady=(12, 4))
            ctk.CTkLabel(card_plug,
                         text="Point to a folder containing plugin subfolders. "
                              "Each valid plugin adds a new entry to the "
                              "Import Games menu.",
                         font=FONT_SMALL, text_color=Palette.MUTED, anchor="w",
                         wraplength=360, justify="left").pack(
                fill="x", padx=16, pady=(2, 8))

            plugin_var = tk.StringVar(value=self._settings.get("plugin_dir", ""))
            plugin_row = ctk.CTkFrame(card_plug, fg_color="transparent")
            plugin_row.pack(fill="x", padx=16, pady=(0, 12))
            ctk.CTkEntry(plugin_row, textvariable=plugin_var,
                         placeholder_text="(none)", font=FONT_MAIN).pack(
                side="left", fill="x", expand=True)

            def browse_plugins():
                d = filedialog.askdirectory(title="Select plugin directory")
                if d:
                    plugin_var.set(d)

            ctk.CTkButton(plugin_row, text="Browse", width=80,
                          fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                          command=browse_plugins).pack(side="left", padx=(8, 0))

            def apply_plugin_dir():
                d = plugin_var.get().strip()
                self._settings["plugin_dir"] = d
                self._save()
                self._reload_plugins(silent=False)
                self._log(f"  Plugin directory set: {d or '(none)'}", "info")

            ctk.CTkButton(card_plug, text="Apply & Reload Plugins",
                          command=apply_plugin_dir,
                          fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                          font=FONT_BOLD).pack(anchor="w", padx=16, pady=(4, 16))

            # ── Update preferences card ──
            card_upd = ctk.CTkFrame(pad, corner_radius=8)
            card_upd.pack(fill="x", pady=(0, 16))
            ctk.CTkLabel(card_upd, text="Update Preferences",
                         font=FONT_BOLD).pack(anchor="w", padx=16, pady=(12, 4))
            ctk.CTkLabel(card_upd,
                         text="When an update is found on startup, show a prompt "
                              "with update options. Disable to suppress the prompt "
                              "— you can still check manually via Menu → Version.",
                         font=FONT_SMALL, text_color=Palette.MUTED, anchor="w",
                         wraplength=360, justify="left").pack(
                fill="x", padx=16, pady=(2, 10))

            update_prompt_var = tk.BooleanVar(
                value=self._settings.get("update_prompt", True))

            def on_update_toggle():
                self._settings["update_prompt"] = update_prompt_var.get()
                self._save()
                self._log(
                    f"  Startup update prompt "
                    f"{'enabled' if update_prompt_var.get() else 'disabled'}.",
                    "info")

            ctk.CTkCheckBox(card_upd,
                            text="Show update prompt on startup",
                            variable=update_prompt_var,
                            command=on_update_toggle,
                            font=FONT_MAIN).pack(anchor="w", padx=16, pady=(0, 4))

            # Show if a pending update is waiting
            pending = self._settings.get("pending_update", "").strip()
            if pending and os.path.isfile(pending):
                ctk.CTkLabel(card_upd,
                             text=f"⏳  Update ready to install on next launch:\n  {pending}",
                             font=FONT_SMALL, text_color=Palette.SUCCESS,
                             anchor="w", wraplength=360,
                             justify="left").pack(fill="x", padx=16, pady=(4, 4))

                def clear_pending():
                    try:
                        if os.path.isfile(pending):
                            os.unlink(pending)
                    except OSError:
                        pass
                    self._settings["pending_update"] = ""
                    self._save()
                    self._log("  Pending update cleared.", "info")
                    win.destroy()
                    self._open_settings()

                ctk.CTkButton(card_upd, text="Cancel pending update",
                              command=clear_pending,
                              fg_color="transparent", border_width=1,
                              font=FONT_SMALL).pack(
                    anchor="w", padx=16, pady=(0, 12))
            else:
                ctk.CTkFrame(card_upd, height=8,
                             fg_color="transparent").pack()

            # ── Danger zone card ──
            card_danger = ctk.CTkFrame(pad, corner_radius=8,
                                        border_width=1, border_color=Palette.ERROR)
            card_danger.pack(fill="x", pady=(0, 16))
            ctk.CTkLabel(card_danger, text="Danger Zone", font=FONT_BOLD,
                         text_color=Palette.ERROR).pack(
                anchor="w", padx=16, pady=(12, 4))
            ctk.CTkLabel(card_danger,
                         text="Uninstall removes all app data stored by "
                              "Omni Game Linker (config, plugin directory, "
                              "accent preference, etc). You will also be asked "
                              "whether to delete your generated .exe output folder.",
                         font=FONT_SMALL, text_color=Palette.MUTED, anchor="w",
                         wraplength=360, justify="left").pack(
                fill="x", padx=16, pady=(4, 10))

            def do_uninstall():
                import shutil
                settings_folder = os.path.dirname(_settings_path())
                confirmed = messagebox.askyesno(
                    "Uninstall — are you sure?",
                    f"This will permanently delete all Omni Game Linker "
                    f"app data:\n\n  {settings_folder}\n\n"
                    "Your generated .exe files will NOT be deleted yet.\n\n"
                    "Continue?",
                    icon="warning")
                if not confirmed:
                    self._log("  Uninstall cancelled.", "info")
                    return

                output_dir    = self.output_dir.get().strip()
                delete_output = False
                if output_dir and os.path.isdir(output_dir):
                    delete_output = messagebox.askyesno(
                        "Delete generated files?",
                        f"Would you also like to delete your output folder "
                        f"and all generated .exe files inside it?\n\n"
                        f"  {output_dir}\n\nThis cannot be undone.",
                        icon="warning")

                # Check if running as a properly installed app —
                # look for the Inno Setup uninstaller next to this exe
                run_windows_uninstall = False
                try:
                    exe_dir       = os.path.dirname(sys.executable)
                    uninstall_exe = os.path.join(exe_dir, "unins000.exe")
                    if os.path.isfile(uninstall_exe):
                        run_windows_uninstall = messagebox.askyesno(
                            "Remove from Windows?",
                            "Would you also like to fully uninstall Omni Game Linker "
                            "from Windows?\n\n"
                            "This will remove the application from:\n"
                            f"  {exe_dir}\n\n"
                            "and clean up Start Menu shortcuts and "
                            "Add/Remove Programs.\n\n"
                            "The Windows uninstaller will open after app data is cleared.",
                            icon="warning")
                except Exception:
                    pass

                try:
                    summary = []
                    if os.path.isdir(settings_folder):
                        shutil.rmtree(settings_folder)
                        self._log(f"  Deleted app data: {settings_folder}", "ok")
                        summary.append(f"App data folder deleted:\n  {settings_folder}")

                    if delete_output:
                        try:
                            shutil.rmtree(output_dir)
                            self._log(f"  Deleted output folder: {output_dir}", "ok")
                            summary.append(f"Output folder deleted:\n  {output_dir}")
                        except Exception as e:
                            self._log(f"⚠  Could not delete output folder: {e}", "err")
                            summary.append(f"Output folder could NOT be deleted:\n  {e}")

                    self._settings = load_settings()
                    self.output_dir.set("")
                    win.destroy()

                    messagebox.showinfo(
                        "Uninstall complete",
                        ("\n\n".join(summary) +
                         "\n\nSettings will reset to defaults on next launch.")
                        if summary else "Nothing was deleted.")

                    # Launch the Windows uninstaller last — after the app
                    # has cleaned up and the settings dialog is closed
                    if run_windows_uninstall:
                        try:
                            subprocess.Popen([uninstall_exe])
                            self._log("  Windows uninstaller launched.", "ok")
                            self.root.after(500, self.root.destroy)
                        except Exception as e:
                            self._log(f"⚠  Could not launch Windows uninstaller: {e}", "err")
                            messagebox.showerror("Uninstaller failed",
                                f"Could not launch the Windows uninstaller:\n{e}\n\n"
                                f"You can run it manually from:\n{uninstall_exe}")

                except Exception as e:
                    self._log(f"⚠  Uninstall failed: {e}", "err")
                    messagebox.showerror("Uninstall failed", str(e))

            ctk.CTkButton(card_danger, text="Uninstall app data…",
                          command=do_uninstall,
                          fg_color="transparent", border_width=1,
                          border_color=Palette.ERROR, text_color=Palette.ERROR,
                          hover_color=Palette.ERROR,
                          font=FONT_BOLD).pack(anchor="w", padx=16, pady=(0, 16))

            # ── Sticky footer ──
            footer = ctk.CTkFrame(win, fg_color="transparent")
            footer.pack(fill="x", padx=24, pady=(6, 18))

            def save_all():
                try:
                    self._settings["plugin_dir"] = plugin_var.get().strip()
                    self._save()
                    self._log("  Settings saved.", "ok")
                except Exception as e:
                    self._log(f"⚠  Save failed: {e}", "err")

            ctk.CTkButton(footer, text="Save", command=save_all, width=80,
                          fg_color=Palette.ACCENT, hover_color=Palette.ACCENT_HOVER,
                          font=FONT_BOLD).pack(side="left")
            ctk.CTkButton(footer, text="Close", command=win.destroy, width=80,
                          fg_color="transparent", border_width=1,
                          font=FONT_MAIN).pack(side="left", padx=(10, 0))

        except Exception as e:
            self._log(f"⚠  Could not open Settings: {e}", "err")

    def _open_version(self):
        try:
            win = ctk.CTkToplevel(self.root)
            win.title("Version")
            win.geometry("340x290")
            win.resizable(False, False)
            win.transient(self.root)
            win.grab_set()

            ctk.CTkLabel(win, text="⚙  Omni Game Linker",
                         font=FONT_BOLD).pack(anchor="w", padx=24, pady=(20, 0))
            ctk.CTkLabel(win, text=f"Version {APP_VERSION}", font=FONT_TITLE,
                         text_color=Palette.ACCENT).pack(
                anchor="w", padx=24, pady=(4, 10))

            pad = ctk.CTkFrame(win, fg_color="transparent")
            pad.pack(fill="x", padx=24)
            for label, value in [
                ("Runtime",  f"Python {sys.version.split()[0]}"),
                ("UI",       "CustomTkinter"),
                ("Compiler", "csc.exe (built-in .NET)"),
                ("Plugins",  f"{len(self._plugins)} loaded"),
            ]:
                row = ctk.CTkFrame(pad, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=label, width=80, font=FONT_MAIN,
                             text_color=Palette.MUTED, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=value, font=FONT_MAIN,
                             anchor="w").pack(side="left", padx=(8, 0))

            # Update check
            status_label = ctk.CTkLabel(win, text="", font=FONT_SMALL,
                                        text_color=Palette.MUTED)
            status_label.pack(pady=(12, 0))

            ctk.CTkButton(win, text="Check for Updates",
                          command=lambda: self._manual_update_check(status_label),
                          width=160, fg_color="transparent", border_width=1,
                          border_color=Palette.ACCENT,
                          text_color=Palette.ACCENT).pack(pady=(6, 4))

            ctk.CTkButton(win, text="Close", command=win.destroy, width=80,
                          fg_color=Palette.ACCENT,
                          hover_color=Palette.ACCENT_HOVER).pack(pady=(4, 18))
        except Exception as e:
            self._log(f"⚠  Could not open Version: {e}", "err")

    # ── Core actions ──────────────────────────────────────────────────────────

    def _browse(self):
        try:
            d = filedialog.askdirectory()
            if d:
                self.output_dir.set(d)
                self._log(f"  Output directory set: {d}", "info")
            else:
                self._log("  Browse cancelled.", "info")
        except Exception as e:
            self._log(f"⚠  Browse failed: {e}", "err")

    def _repack_add_button(self):
        self.btn_add_row.pack_forget()
        self.btn_add_row.pack(anchor="w", padx=10, pady=(4, 6))

    def _add_row(self):
        try:
            self.btn_add_row.pack_forget()
            row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
            self.rows.append(row)
            self.btn_add_row.pack(anchor="w", padx=10, pady=(4, 6))
        except Exception as e:
            self._log(f"⚠  Could not add row: {e}", "err")

    def _remove_row(self, row: Row):
        try:
            if len(self.rows) <= 1:
                self._log("  Cannot remove the last row.", "info")
                return
            name, _ = row.get()
            self.rows.remove(row)
            row.destroy()
            for i, r in enumerate(self.rows):
                r.num_label.configure(text=str(i + 1))
            self._log(f"  Removed row: {name or '(empty)'}", "info")
        except Exception as e:
            self._log(f"⚠  Could not remove row: {e}", "err")

    def _clear_all(self):
        try:
            count = len(self.rows)
            self.btn_add_row.pack_forget()
            for row in list(self.rows):
                row.destroy()
            self.rows.clear()
            self._log_clear()
            self._log(f"  Cleared {count} row(s).", "info")
            self._add_row()
        except Exception as e:
            self._log(f"⚠  Clear all failed: {e}", "err")

    def _consume_blank_row(self):
        if len(self.rows) == 1:
            n, i = self.rows[0].get()
            if not n and not i:
                self.rows[0].destroy()
                self.rows.clear()

    # ── Steam import ──────────────────────────────────────────────────────────

    def _import_from_steam(self):
        self._log("\n── Import from Steam ──", "info")
        self._log("  Searching for Steam installation…", "info")

        def scan():
            try:
                found     = find_steam_shortcuts()
                all_games = find_installed_steam_games() if found else []
                self.root.after(0, lambda: self._on_steam_scan_done(found, all_games))
            except Exception:
                msg = traceback.format_exc()
                self.root.after(0, lambda m=msg: self._log(
                    f"⚠  Steam scan failed:\n    {m}", "err"))

        threading.Thread(target=scan, daemon=True).start()

    def _on_steam_scan_done(self, found, all_games):
        try:
            vdf_path = None
            if not found:
                self._log("  No shortcuts.vdf found automatically.", "info")
                if messagebox.askyesno("Not found",
                        "Could not find Steam's shortcuts.vdf.\n\nBrowse manually?"):
                    vdf_path = filedialog.askopenfilename(
                        title="Select shortcuts.vdf",
                        filetypes=[("VDF files", "shortcuts.vdf"),
                                   ("All files", "*.*")])
                    if vdf_path:
                        found = [("Manual", vdf_path)]
                if not found:
                    self._log("  Import cancelled.", "info")
                    return
            else:
                self._log(f"  Found {len(found)} Steam account(s).", "info")

            if len(found) == 1:
                _, vdf_path = found[0]
            else:
                pick = ctk.CTkToplevel(self.root)
                pick.title("Select Steam Account")
                pick.geometry("300x200")
                pick.grab_set()
                pad = ctk.CTkFrame(pick, fg_color="transparent")
                pad.pack(fill="both", expand=True, padx=20, pady=20)
                ctk.CTkLabel(pad, text="Multiple accounts found. Choose one:",
                             font=FONT_MAIN).pack(pady=(0, 10))
                choice = tk.StringVar(value=found[0][1])
                for label, path in found:
                    ctk.CTkRadioButton(pad, text=label, variable=choice,
                                       value=path, font=FONT_MAIN).pack(
                        anchor="w", pady=4)
                ctk.CTkButton(pad, text="OK", command=pick.destroy,
                              fg_color=Palette.ACCENT,
                              hover_color=Palette.ACCENT_HOVER).pack(pady=(14, 0))
                pick.wait_window()
                vdf_path = choice.get()

            try:
                shortcuts = parse_shortcuts_vdf(vdf_path)
                self._log(f"  Found {len(shortcuts)} non-Steam shortcut(s).", "info")
            except Exception as e:
                self._log(f"⚠  VDF parse failed: {e}", "err")
                messagebox.showerror("Parse Error",
                                     f"Could not read shortcuts.vdf:\n{e}")
                return

            if not shortcuts and not all_games:
                self._log("⚠  No shortcuts or games found.", "err")
                messagebox.showinfo("No games found",
                                    "No shortcuts or installed games found.")
                return

            dlg = SteamImportDialog(self.root, shortcuts, all_games)
            if not dlg.selected:
                self._log("  Import dialog closed with no selection.", "info")
                return

            self._consume_blank_row()
            for name, sid in dlg.selected:
                try:
                    row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
                    row.name_var.set(name)
                    row.id_var.set(sid)
                    self.rows.append(row)
                    self._log(f"    + {name}  (ID: {sid})", "ok")
                except Exception as e:
                    self._log(f"⚠  Could not add row for '{name}': {e}", "err")

            self._repack_add_button()
            self._log(f"  Import complete — {len(dlg.selected)} row(s) added.", "ok")

        except Exception:
            self._log(f"⚠  Steam import failed:\n    {traceback.format_exc()}", "err")

    # ── Epic import ───────────────────────────────────────────────────────────

    def _import_from_epic(self):
        self._log("\n── Import from Epic Games ──", "info")
        self._log("  Scanning Epic manifests…", "info")

        def scan():
            try:
                games = find_epic_games()
                self.root.after(0, lambda: self._on_epic_scan_done(games))
            except Exception:
                msg = traceback.format_exc()
                self.root.after(0, lambda m=msg: self._log(
                    f"⚠  Epic scan failed:\n    {m}", "err"))

        threading.Thread(target=scan, daemon=True).start()

    def _on_epic_scan_done(self, games):
        if not games:
            self._log("⚠  No Epic games found.", "err")
            messagebox.showinfo("No games found",
                "No Epic Games titles found.\nMake sure Epic Launcher is installed.")
            return
        self._log(f"  Found {len(games)} Epic game(s).", "info")
        dlg = ChecklistImportDialog(self.root, "Import from Epic",
                                    "Epic Games Library",
                                    [(n, u) for n, u in games],
                                    show_subtitle=False)
        if not dlg.selected:
            self._log("  Import dialog closed with no selection.", "info")
            return
        self._consume_blank_row()
        for name, uri in dlg.selected:
            try:
                row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
                row.name_var.set(name)
                row.id_var.set(f"EPIC:{uri}")
                self.rows.append(row)
                self._log(f"    + {name}", "ok")
            except Exception as e:
                self._log(f"⚠  Could not add row for '{name}': {e}", "err")
        self._repack_add_button()
        self._log(f"  Import complete — {len(dlg.selected)} row(s) added.", "ok")

    # ── Xbox import ───────────────────────────────────────────────────────────

    def _import_from_xbox(self):
        self._log("\n── Import from Xbox / Microsoft Store ──", "info")
        self._log("  Scanning installed packages (may take a moment)…", "info")

        def scan():
            try:
                games = find_xbox_games()
                self.root.after(0, lambda: self._on_xbox_scan_done(games))
            except Exception:
                msg = traceback.format_exc()
                self.root.after(0, lambda m=msg: self._log(
                    f"⚠  Xbox scan failed:\n    {m}", "err"))

        threading.Thread(target=scan, daemon=True).start()

    def _on_xbox_scan_done(self, games):
        if not games:
            self._log("⚠  No Xbox / MS Store games found.", "err")
            messagebox.showinfo("No games found",
                "No Xbox or MS Store games found.\n"
                "Make sure you have Game Pass titles installed.")
            return
        self._log(f"  Found {len(games)} Xbox game(s).", "info")
        dlg = ChecklistImportDialog(self.root, "Import from Xbox",
                                    "Xbox / Microsoft Store",
                                    [(n, u) for n, u in games],
                                    show_subtitle=False)
        if not dlg.selected:
            self._log("  Import dialog closed with no selection.", "info")
            return
        self._consume_blank_row()
        for name, uri in dlg.selected:
            try:
                row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
                row.name_var.set(name)
                row.id_var.set(f"XBOX:{uri}")
                self.rows.append(row)
                self._log(f"    + {name}", "ok")
            except Exception as e:
                self._log(f"⚠  Could not add row for '{name}': {e}", "err")
        self._repack_add_button()
        self._log(f"  Import complete — {len(dlg.selected)} row(s) added.", "ok")

    # ── Prism import ──────────────────────────────────────────────────────────

    def _import_from_prism(self):
        self._log("\n── Import from Prism Launcher ──", "info")
        self._log("  Searching for Prism Launcher…", "info")

        def scan():
            try:
                prism_exe = find_prism_launcher()
                instances = find_prism_instances()
                self.root.after(0,
                    lambda: self._on_prism_scan_done(prism_exe, instances))
            except Exception:
                msg = traceback.format_exc()
                self.root.after(0, lambda m=msg: self._log(
                    f"⚠  Prism scan failed:\n    {m}", "err"))

        threading.Thread(target=scan, daemon=True).start()

    def _on_prism_scan_done(self, prism_exe, instances):
        try:
            if not prism_exe:
                self._log("⚠  Prism Launcher not found automatically.", "info")
                if messagebox.askyesno("Not found",
                        "Could not find Prism Launcher.\n"
                        "Browse to prismlauncher.exe manually?"):
                    prism_exe = filedialog.askopenfilename(
                        title="Select prismlauncher.exe",
                        filetypes=[("Executable", "prismlauncher.exe"),
                                   ("All files", "*.*")])
                if not prism_exe:
                    self._log("  Import cancelled — Prism not found.", "info")
                    return

            self._log(f"  Prism: {prism_exe}", "info")

            if not instances:
                self._log("⚠  No Prism instances found.", "err")
                messagebox.showinfo("No instances",
                    "No Prism Launcher instances found.\n"
                    "Create at least one instance first.")
                return

            self._log(f"  Found {len(instances)} instance(s).", "info")
            items = [(name, f"PRISM:{iid}|{exe}") for name, iid, exe in instances]
            dlg   = ChecklistImportDialog(self.root, "Import from Prism",
                                          "Prism Launcher Instances", items,
                                          show_subtitle=False)
            if not dlg.selected:
                self._log("  Import dialog closed with no selection.", "info")
                return

            self._consume_blank_row()
            for name, encoded in dlg.selected:
                try:
                    row = Row(self.rows_frame, len(self.rows) + 1, self._remove_row)
                    row.name_var.set(name)
                    row.id_var.set(encoded)
                    self.rows.append(row)
                    self._log(f"    + {name}", "ok")
                except Exception as e:
                    self._log(f"⚠  Could not add row for '{name}': {e}", "err")

            self._repack_add_button()
            self._log(f"  Import complete — {len(dlg.selected)} row(s) added.", "ok")

        except Exception:
            self._log(f"⚠  Prism import failed:\n    {traceback.format_exc()}", "err")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "info"):
        self.log_queue.put((msg, tag))

    def _process_log_queue(self):
        try:
            while True:
                msg, tag = self.log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n", tag)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._process_log_queue)

    def _log_clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Generation ────────────────────────────────────────────────────────────

    def _start_generate(self):
        try:
            if sys.platform != "win32":
                self._log("✕  This tool requires Windows.", "err")
                messagebox.showerror("Unsupported OS",
                                     "This tool requires Windows (csc.exe).")
                return

            self._log_clear()
            self._log("── Generate All ──", "info")

            out_dir = self.output_dir.get().strip()
            if not out_dir:
                self._log("✕  No output directory selected.", "err")
                return

            self._log("  Searching for csc.exe…", "info")
            csc = find_csc()
            if not csc:
                self._log("✕  csc.exe not found — .NET Framework may not be installed.",
                          "err")
                return
            self._log(f"  csc.exe: {csc}", "info")

            entries = [r.get() for r in self.rows]
            valid   = [(n, i) for n, i in entries if n and i]
            for n, i in entries:
                if not n or not i:
                    missing = []
                    if not n:
                        missing.append("name")
                    if not i:
                        missing.append("ID")
                    self._log(
                        f"  Skipping incomplete row "
                        f"(missing {', '.join(missing)}): '{n or '(blank)'}'",
                        "info")

            if not valid:
                self._log("✕  No valid entries to process.", "err")
                return

            self._log(f"  {len(valid)} valid entry(s) to process.", "info")

            confirmed              = []
            auto_confirm_remaining = False

            for idx, (game_name, steam_id) in enumerate(valid, 1):
                if auto_confirm_remaining:
                    try:
                        folder = sanitize_filename(game_name)
                    except ValueError as e:
                        self._log(
                            f"  ⚠  Auto-confirm skipped '{game_name}': {e}", "err")
                        continue
                    confirmed.append((game_name, steam_id, folder))
                    self._log(f"  Auto-confirmed: {game_name} → {folder}/", "info")
                    continue

                try:
                    dlg = FolderNameDialog(self.root, game_name, idx, len(valid))
                except Exception as e:
                    self._log(f"⚠  Folder dialog failed for '{game_name}': {e}", "err")
                    continue

                if dlg.auto_confirm:
                    auto_confirm_remaining = True
                    self._log("  Auto-confirm All activated.", "info")

                if dlg.cancelled or not dlg.result:
                    self._log(f"  Skipped: {game_name}", "info")
                    continue

                confirmed.append((game_name, steam_id, dlg.result))

            if not confirmed:
                self._log("✕  No entries confirmed.", "err")
                return

            self._log(f"  {len(confirmed)} entry(s) confirmed — compiling…", "info")
            self.btn_generate.configure(state="disabled", text="Working…")
            threading.Thread(
                target=self._generate,
                args=(confirmed, out_dir, csc, self._debug_mode.get()),
                daemon=True).start()

        except Exception:
            self._log(f"⚠  Generate setup failed:\n    {traceback.format_exc()}", "err")
            self.btn_generate.configure(state="normal", text="⚡ Generate All")

    def _generate(self, confirmed, out_dir, csc, debug=False):
        try:
            if debug:
                self._log("  Debug mode ON — console window will be visible.", "info")

            if not os.path.isdir(out_dir):
                try:
                    os.makedirs(out_dir)
                    self._log(f"  Created output directory: {out_dir}", "ok")
                except OSError as e:
                    self._log(f"✕  Could not create output directory: {e}", "err")
                    return

            ok_count   = 0
            fail_count = 0

            for game_name, steam_id, folder_name in confirmed:
                self._log(f"\n▸  {game_name}", "info")
                self._log(f"   ID:     {steam_id}", "info")
                self._log(f"   Folder: {folder_name}/", "info")

                game_dir = os.path.join(out_dir, folder_name)
                try:
                    os.makedirs(game_dir, exist_ok=True)
                except OSError as e:
                    self._log(f"   ✕  Could not create folder: {e}", "err")
                    fail_count += 1
                    continue

                self._log("   Compiling .exe…", "info")

                if steam_id.startswith("PRISM:"):
                    try:
                        payload                     = steam_id[len("PRISM:"):]
                        instance_id, prism_exe_path = payload.split("|", 1)
                    except ValueError:
                        self._log(f"   ✕  Malformed Prism entry: {steam_id}", "err")
                        fail_count += 1
                        continue
                    exe_name, err = create_prism_exe(
                        game_name, instance_id, prism_exe_path,
                        game_dir, csc, debug)
                elif steam_id.startswith("EPIC:"):
                    exe_name, err = create_epic_exe(
                        game_name, steam_id[len("EPIC:"):], game_dir, csc, debug)
                elif steam_id.startswith("XBOX:"):
                    exe_name, err = create_xbox_exe(
                        game_name, steam_id[len("XBOX:"):], game_dir, csc, debug)
                else:
                    prefix_match = None
                    if ":" in steam_id:
                        candidate    = steam_id.split(":", 1)[0].upper()
                        prefix_match = self._plugin_prefix_registry.get(candidate)

                    if prefix_match is not None:
                        exe_name, err = prefix_match.create_exe(
                            game_name, steam_id, game_dir, csc, debug)
                        if err == "no_impl":
                            uri = steam_id.split(":", 1)[1]
                            self._log(
                                f"   (plugin '{prefix_match.name}' has no "
                                f"create_exe — using generic URI launcher)", "info")
                            exe_name, err = create_generic_uri_exe(
                                game_name, uri, game_dir, csc, debug)
                    else:
                        exe_name, err = create_exe(
                            game_name, steam_id, game_dir, csc, debug)

                if err:
                    self._log(f"   ✕  Compilation failed: {err}", "err")
                    fail_count += 1
                else:
                    size = 0
                    try:
                        size = os.path.getsize(os.path.join(game_dir, exe_name))
                    except OSError:
                        pass
                    self._log(f"   ✓  {exe_name}  ({size:,} bytes)", "ok")
                    ok_count += 1

            total = len(confirmed)
            self._log("\n── Summary ──", "info")
            self._log(f"   Total:   {total}", "info")
            self._log(f"   Success: {ok_count}",
                      "ok" if ok_count > 0 else "info")
            if fail_count:
                self._log(f"   Failed:  {fail_count}", "err")
            tag = "ok" if ok_count == total else "err"
            self._log(
                f"\n{'✔' if ok_count == total else '⚠'}  "
                f"Done — {ok_count}/{total} completed.", tag)

        except Exception:
            self._log(f"⚠  Generation crashed:\n    {traceback.format_exc()}", "err")
        finally:
            self.root.after(0, lambda: self.btn_generate.configure(
                state="normal", text="⚡ Generate All"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = ctk.CTk()
    App(root)
    root.mainloop()
