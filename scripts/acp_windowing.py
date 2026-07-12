from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Iterable

from acp_common import info, skill_dir, warn
from acp_environment import is_windows


BROWSER_WINDOW_HINTS = [
    "Chrome",
    "Edge",
    "Firefox",
    "Brave",
    "Opera",
    "Internet Explorer",
]

BROWSER_TITLE_HINTS_BY_APP = {
    "chrome": ["Chrome", "Google Chrome"],
    "google chrome": ["Chrome", "Google Chrome"],
    "edge": ["Microsoft Edge"],
    "microsoft edge": ["Microsoft Edge"],
    "firefox": ["Firefox", "Mozilla Firefox"],
    "mozilla firefox": ["Firefox", "Mozilla Firefox"],
    "brave": ["Brave"],
    "brave browser": ["Brave"],
    "opera": ["Opera"],
    "opera browser": ["Opera"],
    "qqbrowser": ["QQBrowser", "QQ浏览器"],
    "qq浏览器": ["QQBrowser", "QQ浏览器"],
    "360se": ["360浏览器", "360"],
    "360浏览器": ["360浏览器", "360"],
}

BROWSER_APP_NAMES = {
    "chrome",
    "google chrome",
    "edge",
    "microsoft edge",
    "firefox",
    "mozilla firefox",
    "chromium",
    "brave",
    "brave browser",
    "opera",
    "opera browser",
    "iexplore",
    "internet explorer",
    "qqbrowser",
    "qq浏览器",
    "360se",
    "360浏览器",
}

DESKTOP_EXECUTABLE_ALIASES = {
    "qq": ["QQ.exe", "QQScLauncher.exe"],
    "tim": ["TIM.exe"],
    "wechat": ["WeChat.exe"],
    "weixin": ["WeChat.exe"],
    "微信": ["WeChat.exe"],
}

DESKTOP_PATH_HINTS = {
    "qq": [
        r"%ProgramFiles%\Tencent\QQNT\QQ.exe",
        r"%ProgramFiles(x86)%\Tencent\QQNT\QQ.exe",
        r"%LOCALAPPDATA%\Programs\Tencent\QQNT\QQ.exe",
        r"%ProgramFiles%\Tencent\QQ\Bin\QQ.exe",
        r"%ProgramFiles(x86)%\Tencent\QQ\Bin\QQ.exe",
        r"%ProgramFiles%\Tencent\QQ\Bin\QQScLauncher.exe",
        r"%ProgramFiles(x86)%\Tencent\QQ\Bin\QQScLauncher.exe",
    ],
    "tim": [
        r"%ProgramFiles%\Tencent\TIM\Bin\TIM.exe",
        r"%ProgramFiles(x86)%\Tencent\TIM\Bin\TIM.exe",
    ],
    "wechat": [
        r"%ProgramFiles%\Tencent\WeChat\WeChat.exe",
        r"%ProgramFiles(x86)%\Tencent\WeChat\WeChat.exe",
        r"%LOCALAPPDATA%\Tencent\WeChat\WeChat.exe",
    ],
    "weixin": [
        r"%ProgramFiles%\Tencent\WeChat\WeChat.exe",
        r"%ProgramFiles(x86)%\Tencent\WeChat\WeChat.exe",
        r"%LOCALAPPDATA%\Tencent\WeChat\WeChat.exe",
    ],
    "微信": [
        r"%ProgramFiles%\Tencent\WeChat\WeChat.exe",
        r"%ProgramFiles(x86)%\Tencent\WeChat\WeChat.exe",
        r"%LOCALAPPDATA%\Tencent\WeChat\WeChat.exe",
    ],
}

ENGLISH_US_KEYBOARD_LAYOUT_ID = "00000409"
CHINESE_SIMPLIFIED_KEYBOARD_LAYOUT_ID = "00000804"
KLF_ACTIVATE = 0x00000001
WM_INPUTLANGCHANGEREQUEST = 0x0050


def iter_visible_windows(win32gui) -> Iterable[tuple[int, str]]:
    def callback(hwnd, acc):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if title:
            acc.append((hwnd, title))
        return True

    windows: list[tuple[int, str]] = []
    win32gui.EnumWindows(callback, windows)
    return windows

def browser_title_hints_for_app(app_name: str) -> list[str]:
    normalized = app_name.strip().lower()
    hints = BROWSER_TITLE_HINTS_BY_APP.get(normalized, [])
    if not hints and app_name.strip():
        hints = [app_name.strip()]
    return hints

def window_matches_application(title: str, app_name: str, target: str) -> bool:
    lower = title.lower()
    app_lower = app_name.strip().lower()
    if target == "web":
        hints = browser_title_hints_for_app(app_name)
        if hints:
            return any(hint.lower() in lower for hint in hints)
        return bool(app_lower and app_lower in lower)
    if app_lower and app_lower in lower:
        return True
    return False

def bring_window_to_front(app_name: str, target: str, win32con, win32gui) -> bool:
    app_lower = app_name.lower()
    windows = list(iter_visible_windows(win32gui))

    def score(title: str) -> int:
        lower = title.lower()
        value = 0
        if app_lower in lower:
            value += 10
        if target == "web" and any(hint.lower() in lower for hint in BROWSER_WINDOW_HINTS):
            value += 4
        return value

    candidates = sorted(
        [(score(title), hwnd, title) for hwnd, title in windows if score(title) > 0],
        reverse=True,
    )

    if not candidates:
        if target == "web":
            warn("没有找到标题匹配的浏览器窗口，将继续使用当前前台窗口。")
            return False
        warn(f"没有找到标题包含“{app_name}”的窗口，将继续使用当前前台窗口。")
        return False

    _, hwnd, title = candidates[0]
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.6)
        info(f"已置前窗口：{title}")
        return True
    except Exception as exc:
        warn(f"窗口置前失败，将继续使用当前前台窗口：{exc}")
        return False

def close_application_windows(
    app_name: str,
    target: str,
    win32con,
    win32gui,
    *,
    timeout: float = 5.0,
) -> int:
    windows = [
        (hwnd, title)
        for hwnd, title in iter_visible_windows(win32gui)
        if window_matches_application(title, app_name, target)
    ]
    if not windows:
        info(f"未发现需要关闭的 {app_name} 窗口。")
        return 0

    for hwnd, title in windows:
        try:
            info(f"关闭已有 {app_name} 窗口：{title}")
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception as exc:
            warn(f"关闭窗口失败：{title}；{exc}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = [
            title
            for _, title in iter_visible_windows(win32gui)
            if window_matches_application(title, app_name, target)
        ]
        if not remaining:
            break
        time.sleep(0.5)

    return len(windows)

def wait_for_window_to_front(
    app_name: str,
    target: str,
    win32con,
    win32gui,
    *,
    timeout: float = 8.0,
    interval: float = 0.8,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if bring_window_to_front(app_name, target, win32con, win32gui):
            return True
        time.sleep(interval)
    return bring_window_to_front(app_name, target, win32con, win32gui)

def infer_target_type(app_name: str) -> str:
    normalized = app_name.strip().lower()
    if normalized in BROWSER_APP_NAMES or "browser" in normalized or "浏览器" in normalized:
        target = "web"
    else:
        target = "desktop"
    info(f"根据应用名称自动识别目标类型：{target}")
    return target

def executable_names_for_app(app_name: str) -> list[str]:
    normalized = app_name.strip().lower()
    names = [app_name.strip()]
    names.extend(DESKTOP_EXECUTABLE_ALIASES.get(normalized, []))
    if names[0] and not names[0].lower().endswith(".exe"):
        names.append(f"{names[0]}.exe")
    return list(dict.fromkeys(name for name in names if name))

def existing_path(path_text: str) -> Path | None:
    expanded = Path(os.path.expandvars(path_text.strip('"')))
    return expanded if expanded.exists() else None

def find_app_from_asset_config(app_name: str) -> Path | str | None:
    config_file = skill_dir() / "assets" / app_name / "appPath.txt"
    if not config_file.exists():
        return None

    for raw_line in config_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().replace("\ufeff", "")
        if not line or line.startswith("#"):
            continue
        path = existing_path(line)
        if path:
            return path
        return line
    return None

def find_app_from_path(app_name: str) -> Path | None:
    for exe_name in executable_names_for_app(app_name):
        found = shutil.which(exe_name)
        if found:
            return Path(found)
    return None

def find_app_from_registry(app_name: str) -> Path | None:
    if not is_windows():
        return None
    try:
        import winreg
    except Exception:
        return None

    root_keys = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    subkey_prefixes = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
    ]
    for root_key in root_keys:
        for prefix in subkey_prefixes:
            for exe_name in executable_names_for_app(app_name):
                try:
                    with winreg.OpenKey(root_key, rf"{prefix}\{exe_name}") as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        path = existing_path(value)
                        if path:
                            return path
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
    return None

def find_app_from_known_paths(app_name: str) -> Path | None:
    normalized = app_name.strip().lower()
    for hint in DESKTOP_PATH_HINTS.get(normalized, []):
        path = existing_path(hint)
        if path:
            return path
    return None

def find_app_shortcut(app_name: str) -> Path | None:
    normalized = app_name.strip().lower()
    shortcut_roots = [
        Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    aliases = {normalized}
    for exe_name in executable_names_for_app(app_name):
        aliases.add(Path(exe_name).stem.lower())

    for root in shortcut_roots:
        if not root.exists():
            continue
        try:
            for shortcut in root.rglob("*.lnk"):
                name = shortcut.stem.lower()
                if any(alias and alias in name for alias in aliases):
                    return shortcut
        except OSError:
            continue
    return None

def common_install_roots() -> list[Path]:
    candidates = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"),
    ]
    roots: list[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(os.path.expandvars(candidate))
        if path.exists() and path not in roots:
            roots.append(path)
    return roots

def find_app_from_common_install_dirs(app_name: str, *, time_limit: float = 5.0) -> Path | None:
    normalized = app_name.strip().lower()
    if not normalized:
        return None

    aliases = {normalized}
    for exe_name in executable_names_for_app(app_name):
        aliases.add(Path(exe_name).stem.lower())

    deadline = time.time() + time_limit
    fallback: Path | None = None
    for root in common_install_roots():
        if time.time() > deadline:
            break
        try:
            for current, dirs, files in os.walk(root):
                if time.time() > deadline:
                    break
                current_path = Path(current)
                try:
                    depth = len(current_path.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth >= 5:
                    dirs[:] = []

                current_lower = current_path.name.lower()
                folder_matches = normalized in current_lower or any(alias in current_lower for alias in aliases)
                for file_name in files:
                    file_path = current_path / file_name
                    suffix = file_path.suffix.lower()
                    if suffix not in {".exe", ".lnk"}:
                        continue
                    stem = file_path.stem.lower()
                    if stem in aliases:
                        return file_path
                    if normalized in stem:
                        fallback = fallback or file_path
                    elif folder_matches and any(alias in stem or stem in alias for alias in aliases):
                        fallback = fallback or file_path
        except OSError:
            continue
    return fallback

def resolve_application_launcher(app_name: str) -> Path | str | None:
    return (
        find_app_from_asset_config(app_name)
        or find_app_from_path(app_name)
        or find_app_from_registry(app_name)
        or find_app_from_known_paths(app_name)
        or find_app_shortcut(app_name)
        or find_app_from_common_install_dirs(app_name)
    )

def launch_application(app_name: str) -> bool:
    launcher = resolve_application_launcher(app_name)
    if launcher:
        try:
            if isinstance(launcher, Path):
                os.startfile(str(launcher))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(launcher, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            info(f"已启动应用：{app_name} -> {launcher}")
            time.sleep(2.0)
            return True
        except Exception as exc:
            warn(f"启动应用失败：{launcher}；{exc}")

    try:
        executable = executable_names_for_app(app_name)[0]
        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        info(f"已尝试通过可执行名称启动应用：{executable}")
        time.sleep(2.0)
        return True
    except Exception as exc:
        warn(f"未找到或无法启动应用“{app_name}”：{exc}")
        warn(f"如果应用已经打开，工具会继续尝试前置已有窗口；如果没有打开，请先手动打开应用，或在 assets\\{app_name}\\appPath.txt 写入应用 exe/快捷方式路径。")
        return False

def open_web_url(app_name: str, url: str) -> None:
    try:
        subprocess.Popen(["cmd", "/c", "start", "", app_name, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        info(f"已使用 {app_name} 打开地址：{url}")
    except Exception as exc:
        warn(f"使用 {app_name} 打开地址失败，将使用系统默认浏览器：{exc}")
        webbrowser.open(url)
    time.sleep(3.0)

def close_foreground_window(pyautogui, *, label: str) -> None:
    info(f"关闭当前窗口：{label}")
    pyautogui.hotkey("alt", "f4")
    time.sleep(1.0)

def switch_keyboard_layout(win32gui, layout_id: str, label: str) -> bool:
    if not is_windows():
        return True

    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
        user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
        user32.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, wintypes.UINT]
        user32.ActivateKeyboardLayout.restype = ctypes.c_void_p
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        user32.GetKeyboardLayout.restype = ctypes.c_void_p

        hkl = user32.LoadKeyboardLayoutW(layout_id, KLF_ACTIVATE)
        if not hkl:
            warn(f"切换{label}输入法失败：无法加载键盘布局 {layout_id}。")
            return False

        user32.ActivateKeyboardLayout(ctypes.c_void_p(hkl), KLF_ACTIVATE)
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, int(hkl))
            time.sleep(0.2)
            thread_id = user32.GetWindowThreadProcessId(hwnd, None)
            current_hkl = user32.GetKeyboardLayout(thread_id)
            current_lang_id = int(current_hkl or 0) & 0xFFFF
            info(f"已请求切换输入法为{label}键盘布局，当前前台窗口键盘语言 ID：0x{current_lang_id:04x}")
        else:
            info(f"已请求切换输入法为{label}键盘布局。")
        return True
    except Exception as exc:
        warn(f"切换{label}输入法失败，将继续执行：{exc}")
        return False


def switch_to_english_input_method(win32gui) -> bool:
    """Request English US keyboard layout for the foreground window before typing.

    pyautogui.write sends key strokes, so an active Chinese IME can intercept
    letters into composition/candidate mode. Loading and activating the US
    keyboard layout before typing keeps account/password input literal.
    """
    return switch_keyboard_layout(win32gui, ENGLISH_US_KEYBOARD_LAYOUT_ID, "英文")


def switch_to_chinese_input_method(win32gui) -> bool:
    """Request Simplified Chinese keyboard layout after login completes."""
    return switch_keyboard_layout(win32gui, CHINESE_SIMPLIFIED_KEYBOARD_LAYOUT_ID, "中文")
