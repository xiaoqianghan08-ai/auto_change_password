#!/usr/bin/env python3
"""Create annotated screenshots for auto-change-password image matching."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


SUFFIXES = [
    "input_password_window",
    "input_account",
    "input_password",
    "login_button",
    "save_password_window",
    "save_password",
    "update_password",
]

MATCH_SCALES = [1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15]

PYTHON_DEPENDENCIES = [
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pyautogui", "PyAutoGUI"),
    ("pyscreeze", "pyscreeze"),
    ("PIL", "pillow"),
]


@dataclass
class MatchResult:
    suffix: str
    template: str
    exists: bool
    found: bool
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    confidence: float | None = None
    scale: float | None = None
    grayscale: bool | None = None
    note: str | None = None


def fail(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}")
    raise SystemExit(code)


def info(message: str) -> None:
    print(f"[INFO] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


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


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def image_name(app_name: str, suffix: str) -> str:
    return f"{app_name}_{suffix}.png"


def import_dependencies():
    try:
        import cv2
        import numpy as np
        import pyautogui
        from PIL import Image
    except ImportError as exc:
        fail(
            "缺少依赖。请先运行：python -m pip install -r requirements.txt\n"
            f"原始错误：{exc}"
        )
    return cv2, np, pyautogui, Image


def locate_with_cv(cv2, screenshot_bgr, template_path: Path, threshold: float) -> tuple[bool, tuple[int, int, int, int] | None, float | None, float | None, bool | None]:
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return False, None, None, None, None

    screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    screen_height, screen_width = screenshot_bgr.shape[:2]
    best_score = -1.0
    best_box: tuple[int, int, int, int] | None = None
    best_scale: float | None = None
    best_grayscale: bool | None = None

    for scale in MATCH_SCALES:
        width = int(template.shape[1] * scale)
        height = int(template.shape[0] * scale)
        if width < 3 or height < 3:
            continue
        if width > screen_width or height > screen_height:
            continue

        resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
        resized_gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        for grayscale, haystack, needle in [
            (False, screenshot_bgr, resized),
            (True, screenshot_gray, resized_gray),
        ]:
            result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = float(max_val)
                best_box = (int(max_loc[0]), int(max_loc[1]), int(width), int(height))
                best_scale = scale
                best_grayscale = grayscale

    if best_box and best_score >= threshold:
        return True, best_box, best_score, best_scale, best_grayscale
    return False, best_box, best_score if best_score >= 0 else None, best_scale, best_grayscale


def run(app_name: str, confidence: float, output_dir: Path | None) -> int:
    if platform.system().lower() != "windows":
        fail("此 debug 工具仅支持 Windows 桌面环境。")

    ensure_python_dependencies()

    cv2, np, pyautogui, Image = import_dependencies()
    app_dir = skill_dir() / "assets" / app_name
    if not app_dir.exists():
        fail(f"应用图片目录不存在：{app_dir}")

    output_dir = output_dir or (skill_dir() / "debug_output" / f"{app_name}_{time.strftime('%Y%m%d_%H%M%S')}")
    output_dir.mkdir(parents=True, exist_ok=True)

    screenshot = pyautogui.screenshot()
    screenshot_path = output_dir / "desktop_screenshot.png"
    screenshot.save(screenshot_path)

    screenshot_rgb = np.array(screenshot)
    screenshot_bgr = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2BGR)
    annotated = screenshot_bgr.copy()

    results: list[MatchResult] = []
    colors = [
        (0, 255, 0),
        (255, 0, 0),
        (0, 128, 255),
        (255, 0, 255),
        (255, 255, 0),
        (0, 255, 255),
        (128, 255, 128),
    ]

    for idx, suffix in enumerate(SUFFIXES):
        template = app_dir / image_name(app_name, suffix)
        if not template.exists():
            results.append(MatchResult(suffix=suffix, template=str(template), exists=False, found=False))
            continue

        found, box, score, scale, grayscale = locate_with_cv(cv2, screenshot_bgr, template, confidence)
        if box:
            left, top, width, height = box
            color = colors[idx % len(colors)]
            thickness = 2 if found else 1
            cv2.rectangle(annotated, (left, top), (left + width, top + height), color, thickness)
            cv2.putText(
                annotated,
                suffix if found else f"{suffix}:best={score:.2f}" if score is not None else suffix,
                (left, max(20, top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )
            results.append(
                MatchResult(
                    suffix=suffix,
                    template=str(template),
                    exists=True,
                    found=found,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    confidence=score,
                    scale=scale,
                    grayscale=grayscale,
                    note=None if found else "below_threshold_best_location",
                )
            )
        else:
            results.append(
                MatchResult(
                    suffix=suffix,
                    template=str(template),
                    exists=True,
                    found=False,
                    confidence=score,
                    scale=scale,
                    grayscale=grayscale,
                    note="no_match_result",
                )
            )

    annotated_path = output_dir / "annotated_matches.png"
    cv2.imwrite(str(annotated_path), annotated)

    summary_path = output_dir / "match_summary.json"
    summary_path.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] 桌面截图：{screenshot_path}")
    print(f"[OK] 标注图片：{annotated_path}")
    print(f"[OK] 匹配摘要：{summary_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="生成桌面截图和模板匹配标注图。")
    parser.add_argument("--app", required=True, help="应用名称，对应 assets/<应用名称>/ 文件夹。")
    parser.add_argument("--confidence", type=float, default=0.86, help="图片匹配阈值，默认 0.86。")
    parser.add_argument("--output-dir", type=Path, help="输出目录，默认写入 skill/debug_output/。")
    args = parser.parse_args()
    return run(args.app, args.confidence, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
