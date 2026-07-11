from __future__ import annotations

import time
from pathlib import Path

from acp_common import Box, SAVE_OPTIONAL_SUFFIXES, info, warn
from acp_debug import run_debug_tool_automatically
from acp_input_actions import click_box
from acp_vision import locate_with_multiscale_cv2, locate_with_retries


def locate_save_prompt_template(
    pyautogui,
    image_path: Path,
    *,
    label: str,
    region: Box | None = None,
    confidence: float,
    min_confidence: float,
) -> tuple[Box | None, float | None]:
    if not image_path.exists():
        return None, None

    box, used_confidence = locate_with_retries(
        pyautogui,
        image_path,
        region=region,
        confidence=confidence,
        min_confidence=min_confidence,
        attempts=1,
        retry_wait=0.0,
        grayscale_fallback=True,
    )
    if box:
        return box, used_confidence

    box, best_score, _, _ = locate_with_multiscale_cv2(
        pyautogui,
        image_path,
        region=region,
        min_confidence=min_confidence,
    )
    if box:
        return box, best_score

    return None, best_score

def handle_save_update_password_prompt(
    pyautogui,
    paths: dict[str, Path],
    *,
    app_name: str,
    confidence: float,
    initial_wait: float,
    timeout: float,
    retry_wait: float,
) -> None:
    available = {suffix: paths[suffix].exists() for suffix in SAVE_OPTIONAL_SUFFIXES}
    if not any(available.values()):
        return

    info("等待保存/更新密码提示窗口出现。")
    time.sleep(max(0.0, initial_wait))

    if not available["save_password_window"]:
        warn("缺少 save_password_window 模板，将直接全屏搜索保存/更新按钮。")
    if not available["update_password"] and not available["save_password"]:
        warn("缺少 save_password/update_password 按钮模板，无法自动点击保存/更新密码。")
        return

    deadline = time.monotonic() + max(0.1, timeout)
    attempt = 0
    last_window_score: float | None = None

    while time.monotonic() <= deadline:
        attempt += 1
        info(f"第 {attempt} 轮搜索保存/更新密码提示，全屏搜索 save_password_window。")

        save_window: Box | None = None
        if available["save_password_window"]:
            save_window, last_window_score = locate_save_prompt_template(
                pyautogui,
                paths["save_password_window"],
                label="保存/更新密码窗口",
                region=None,
                confidence=min(confidence, 0.80),
                min_confidence=0.65,
            )
            if save_window:
                info(
                    "识别到 保存/更新密码窗口："
                    f"left={save_window.left}, top={save_window.top}, "
                    f"width={save_window.width}, height={save_window.height}"
                )

        search_regions: list[tuple[str, Box | None]] = []
        if save_window:
            search_regions.append(("保存/更新密码窗口区域", save_window))
        search_regions.append(("全屏", None))

        for region_label, region in search_regions:
            if available["update_password"]:
                update_button, _ = locate_save_prompt_template(
                    pyautogui,
                    paths["update_password"],
                    label="更新密码",
                    region=region,
                    confidence=confidence,
                    min_confidence=0.70,
                )
                if update_button:
                    info(f"在{region_label}识别到 更新密码 按钮。")
                    click_box(pyautogui, update_button, "更新密码")
                    return

            if available["save_password"]:
                save_button, _ = locate_save_prompt_template(
                    pyautogui,
                    paths["save_password"],
                    label="保存密码",
                    region=region,
                    confidence=confidence,
                    min_confidence=0.70,
                )
                if save_button:
                    info(f"在{region_label}识别到 保存密码 按钮。")
                    click_box(pyautogui, save_button, "保存密码")
                    return

        if time.monotonic() < deadline:
            warn(f"本轮未识别到保存/更新密码按钮，等待 {retry_wait:.1f} 秒后重试。")
            time.sleep(max(0.1, retry_wait))

    if last_window_score is not None:
        warn(f"保存/更新密码窗口最终未命中；save_password_window 最高匹配分数约为 {last_window_score:.3f}。")
    warn("未识别到保存/更新密码提示或按钮，自动执行 debug_tool.py 生成排查图片。")
    run_debug_tool_automatically(
        app_name,
        min(confidence, 0.70),
        "保存/更新密码提示识别失败",
    )
