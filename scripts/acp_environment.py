from __future__ import annotations

import ctypes
import importlib.util
import platform
import subprocess
import sys

from acp_common import fail, info, warn


PYTHON_DEPENDENCIES = [
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pyautogui", "PyAutoGUI"),
    ("pyscreeze", "pyscreeze"),
    ("PIL", "pillow"),
    ("pyperclip", "pyperclip"),
    ("win32con", "pywin32"),
    ("win32gui", "pywin32"),
]


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None

def ensure_pip() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode == 0:
        return True

    warn("当前 Python 没有可用 pip，尝试启用 ensurepip。")
    ensurepip = subprocess.run(
        [sys.executable, "-m", "ensurepip", "--upgrade"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if ensurepip.returncode != 0:
        warn(ensurepip.stdout.strip())
        return False
    return True

def install_package(package_name: str) -> bool:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        package_name,
    ]
    info(f"检测到缺少依赖，正在安装：{package_name}")
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode == 0:
        info(f"依赖安装成功：{package_name}")
        return True
    warn(f"依赖安装失败：{package_name}")
    if result.stdout:
        warn(result.stdout.strip())
    return False

def ensure_python_dependencies() -> None:
    missing_packages: list[str] = []
    for module_name, package_name in PYTHON_DEPENDENCIES:
        if not module_available(module_name) and package_name not in missing_packages:
            missing_packages.append(package_name)

    if not missing_packages:
        return

    if not ensure_pip():
        fail(
            "缺少依赖且无法启用 pip，请手动安装：\n"
            f"{sys.executable} -m pip install {' '.join(missing_packages)}"
        )

    failed_packages: list[str] = []
    for package_name in missing_packages:
        if not install_package(package_name):
            failed_packages.append(package_name)

    still_missing = [
        package_name
        for module_name, package_name in PYTHON_DEPENDENCIES
        if package_name in missing_packages and not module_available(module_name)
    ]
    for package_name in still_missing:
        if package_name not in failed_packages:
            failed_packages.append(package_name)

    if failed_packages:
        fail(
            "依赖自动安装失败，请检查网络或 Python 环境后手动安装：\n"
            f"{sys.executable} -m pip install {' '.join(failed_packages)}"
        )

def is_windows() -> bool:
    return platform.system().lower() == "windows"

def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def import_gui_dependencies():
    try:
        import cv2  # noqa: F401
        import pyperclip
        import pyautogui
        import win32con
        import win32gui
    except ImportError as exc:
        fail(
            "缺少依赖。请先运行：python -m pip install -r requirements.txt\n"
            f"原始错误：{exc}"
        )
    return pyautogui, pyperclip, win32con, win32gui
