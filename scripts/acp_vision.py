from __future__ import annotations

import time
from pathlib import Path

from acp_common import Box, SAVE_PROMPT_SCALES, info, warn
from acp_debug import run_debug_tool_automatically


def locate(
    pyautogui,
    image_path: Path,
    *,
    region: Box | None = None,
    confidence: float = 0.86,
    grayscale: bool = False,
) -> Box | None:
    search_region = region.as_region() if region else None
    try:
        found = pyautogui.locateOnScreen(
            str(image_path),
            confidence=confidence,
            region=search_region,
            grayscale=grayscale,
        )
    except Exception as exc:
        warn(f"识别图片失败：{image_path.name}；{exc}")
        return None
    if not found:
        return None
    return Box(int(found.left), int(found.top), int(found.width), int(found.height))

def locate_with_retries(
    pyautogui,
    image_path: Path,
    *,
    region: Box | None = None,
    confidence: float = 0.86,
    min_confidence: float = 0.70,
    attempts: int = 1,
    retry_wait: float = 0.0,
    grayscale_fallback: bool = False,
) -> tuple[Box | None, float | None]:
    if not image_path.exists():
        warn(f"模板不存在，跳过识别：{image_path.name}")
        return None, None

    attempts = max(1, attempts)
    confidences: list[float] = []
    for value in [confidence, confidence - 0.06, confidence - 0.12, min_confidence]:
        value = round(max(min_confidence, value), 2)
        if value not in confidences:
            confidences.append(value)

    grayscale_modes = [False, True] if grayscale_fallback else [False]

    for attempt in range(1, attempts + 1):
        for current_confidence in confidences:
            for grayscale in grayscale_modes:
                box = locate(
                    pyautogui,
                    image_path,
                    region=region,
                    confidence=current_confidence,
                    grayscale=grayscale,
                )
                if box:
                    if attempt > 1:
                        info(f"{image_path.name} 第 {attempt} 轮识别成功。")
                    if grayscale:
                        info(f"{image_path.name} 使用灰度匹配识别成功。")
                    return box, current_confidence
        if attempt < attempts:
            warn(f"{image_path.name} 第 {attempt} 轮识别失败，等待 {retry_wait:.1f} 秒后重新截图识别。")
            time.sleep(max(0.0, retry_wait))
    return None, None

def locate_with_multiscale_cv2(
    pyautogui,
    image_path: Path,
    *,
    region: Box | None = None,
    min_confidence: float = 0.65,
    scales: list[float] | None = None,
) -> tuple[Box | None, float | None, float | None, bool | None]:
    if not image_path.exists():
        return None, None, None, None

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        warn(f"OpenCV 多尺度识别依赖缺失，跳过：{exc}")
        return None, None, None, None

    search_region = region.as_region() if region else None
    offset_left = region.left if region else 0
    offset_top = region.top if region else 0

    try:
        screenshot = pyautogui.screenshot(region=search_region)
    except Exception as exc:
        warn(f"截图失败，无法进行多尺度识别：{exc}")
        return None, None, None, None

    screenshot_rgb = np.array(screenshot)
    screenshot_bgr = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2BGR)
    screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    template_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if template_bgr is None:
        warn(f"模板图片无法读取，跳过多尺度识别：{image_path.name}")
        return None, None, None, None

    screen_height, screen_width = screenshot_bgr.shape[:2]
    scales = scales or SAVE_PROMPT_SCALES
    best_score = -1.0
    best_box: Box | None = None
    best_scale: float | None = None
    best_grayscale: bool | None = None

    for scale in scales:
        resized_width = int(template_bgr.shape[1] * scale)
        resized_height = int(template_bgr.shape[0] * scale)
        if resized_width < 3 or resized_height < 3:
            continue
        if resized_width > screen_width or resized_height > screen_height:
            continue

        resized_bgr = cv2.resize(template_bgr, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
        resized_gray = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2GRAY)

        for grayscale, haystack, needle in [
            (False, screenshot_bgr, resized_bgr),
            (True, screenshot_gray, resized_gray),
        ]:
            result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = float(max_val)
                best_box = Box(
                    left=offset_left + int(max_loc[0]),
                    top=offset_top + int(max_loc[1]),
                    width=resized_width,
                    height=resized_height,
                )
                best_scale = scale
                best_grayscale = grayscale

    if best_box and best_score >= min_confidence:
        info(
            f"{image_path.name} 多尺度识别成功：confidence={best_score:.3f}, "
            f"scale={best_scale}, grayscale={best_grayscale}"
        )
        return best_box, best_score, best_scale, best_grayscale

    if best_box:
        warn(
            f"{image_path.name} 多尺度最高匹配未达阈值：best={best_score:.3f}, "
            f"threshold={min_confidence}, left={best_box.left}, top={best_box.top}, "
            f"width={best_box.width}, height={best_box.height}, scale={best_scale}, grayscale={best_grayscale}"
        )
    return None, best_score if best_score >= 0 else None, best_scale, best_grayscale

def center_delta(first: Box, second: Box) -> tuple[int, int]:
    first_x, first_y = first.center
    second_x, second_y = second.center
    return abs(first_x - second_x), abs(first_y - second_y)

def clamp_box_to_screen(pyautogui, box: Box) -> Box:
    screen_width, screen_height = pyautogui.size()
    left = max(0, min(box.left, screen_width - 1))
    top = max(0, min(box.top, screen_height - 1))
    right = max(left + 1, min(box.left + box.width, screen_width))
    bottom = max(top + 1, min(box.top + box.height, screen_height))
    return Box(left=left, top=top, width=right - left, height=bottom - top)

def union_boxes(boxes: list[Box]) -> Box:
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.left + box.width for box in boxes)
    bottom = max(box.top + box.height for box in boxes)
    return Box(left=left, top=top, width=right - left, height=bottom - top)

def expand_box(pyautogui, box: Box, *, left: int, top: int, right: int, bottom: int) -> Box:
    return clamp_box_to_screen(
        pyautogui,
        Box(
            left=box.left - left,
            top=box.top - top,
            width=box.width + left + right,
            height=box.height + top + bottom,
        ),
    )

def choose_field_box(label: str, inferred: Box, template_box: Box | None, used_confidence: float | None) -> Box:
    if not template_box:
        warn(f"未识别到 {label} 模板，将使用布局推断位置点击；如果点击不准，请把模板截图改为包含完整输入框本体。")
        info(
            f"{label} 使用布局推断位置："
            f"left={inferred.left}, top={inferred.top}, width={inferred.width}, height={inferred.height}"
        )
        return inferred

    info(
        f"{label} 模板识别成功，使用模板中心点击聚焦。"
        f" template=({template_box.left},{template_box.top},{template_box.width},{template_box.height}),"
        f" inferred=({inferred.left},{inferred.top},{inferred.width},{inferred.height}),"
        f" confidence={used_confidence}"
    )
    return template_box

def infer_login_window_from_elements(
    pyautogui,
    *,
    login_button: Box,
    account_box: Box | None = None,
    password_box: Box | None = None,
) -> Box:
    elements = [box for box in [account_box, password_box, login_button] if box is not None]
    if len(elements) >= 2:
        base = union_boxes(elements)
        horizontal = max(30, int(base.width * 0.06))
        top_padding = max(160, int(base.height * 0.45))
        bottom_padding = max(24, int(login_button.height * 0.35))
        inferred = expand_box(
            pyautogui,
            base,
            left=horizontal,
            top=top_padding,
            right=horizontal,
            bottom=bottom_padding,
        )
    else:
        inferred = expand_box(
            pyautogui,
            login_button,
            left=max(35, int(login_button.width * 0.06)),
            top=max(300, int(login_button.height * 3.2)),
            right=max(35, int(login_button.width * 0.06)),
            bottom=max(30, int(login_button.height * 0.4)),
        )

    warn(
        "账号密码输入窗口模板未识别，将根据子元素反推窗口区域："
        f"left={inferred.left}, top={inferred.top}, width={inferred.width}, height={inferred.height}"
    )
    return inferred

def infer_account_box(login_window: Box, password_box: Box, login_button: Box | None = None) -> Box:
    if login_button and login_button.top > password_box.top:
        vertical_offset = login_button.top - password_box.top
    else:
        vertical_offset = password_box.height * 2

    vertical_offset = max(password_box.height + 12, min(vertical_offset, password_box.height * 4))
    inferred_top = max(login_window.top, password_box.top - vertical_offset)
    inferred_left = max(login_window.left, password_box.left)
    inferred_width = min(password_box.width, login_window.left + login_window.width - inferred_left)

    return Box(
        left=inferred_left,
        top=inferred_top,
        width=max(1, inferred_width),
        height=password_box.height,
    )

def infer_password_box(login_window: Box, login_button: Box) -> Box:
    field_height = max(
        1,
        min(
            max(login_button.height, int(login_window.height * 0.17)),
            int(login_window.height * 0.24),
        ),
    )
    gap = max(6, int(login_window.height * 0.012))
    horizontal_padding = max(0, int(login_button.width * 0.03))
    inferred_left = max(login_window.left, login_button.left + horizontal_padding)
    inferred_width = min(
        max(1, int(login_button.width * 0.95)),
        login_window.left + login_window.width - inferred_left,
    )
    inferred_top = max(login_window.top, login_button.top - field_height - gap)

    return Box(
        left=inferred_left,
        top=inferred_top,
        width=max(1, inferred_width),
        height=max(1, field_height),
    )

def locate_password_box(
    pyautogui,
    image_path: Path,
    *,
    login_window: Box,
    login_button: Box,
    confidence: float,
    attempts: int,
    retry_wait: float,
) -> Box:
    inferred = infer_password_box(login_window, login_button)
    box, used_confidence = locate_with_retries(
        pyautogui,
        image_path,
        region=login_window,
        confidence=confidence,
        min_confidence=0.68,
        attempts=attempts,
        retry_wait=retry_wait,
    )
    if not box:
        warn("未识别到密码输入框辅助模板，将根据登录按钮位置推断密码输入框。")
    elif used_confidence is not None and used_confidence < confidence:
        warn(f"密码输入框辅助模板使用较低置信度识别成功：{used_confidence}")
    return choose_field_box("密码输入框", inferred, box, used_confidence)

def locate_account_box(
    pyautogui,
    image_path: Path,
    *,
    login_window: Box,
    password_box: Box,
    login_button: Box,
    confidence: float,
    attempts: int,
    retry_wait: float,
) -> Box:
    inferred = infer_account_box(login_window, password_box, login_button)
    box, used_confidence = locate_with_retries(
        pyautogui,
        image_path,
        region=login_window,
        confidence=confidence,
        min_confidence=0.68,
        attempts=attempts,
        retry_wait=retry_wait,
    )
    if not box:
        warn("未识别到账号输入框辅助模板，将根据密码框和登录按钮位置推断账号输入框。")
    elif used_confidence is not None and used_confidence < confidence:
        warn(f"账号输入框辅助模板使用较低置信度识别成功：{used_confidence}")
    return choose_field_box("账号输入框", inferred, box, used_confidence)

def require_locate(
    pyautogui,
    image_path: Path,
    label: str,
    *,
    region: Box | None = None,
    confidence: float = 0.86,
    app_name: str | None = None,
    attempts: int = 1,
    retry_wait: float = 0.0,
) -> Box:
    box, _ = locate_with_retries(
        pyautogui,
        image_path,
        region=region,
        confidence=confidence,
        min_confidence=confidence,
        attempts=attempts,
        retry_wait=retry_wait,
    )
    if not box:
        if app_name:
            run_debug_tool_automatically(
                app_name,
                confidence,
                f"未识别到 {label}：{image_path.name}",
            )
        fail(f"未识别到 {label}：{image_path.name}。请运行 debug_tool.py 生成排查图片。")
    info(f"识别到 {label}：left={box.left}, top={box.top}, width={box.width}, height={box.height}")
    return box
