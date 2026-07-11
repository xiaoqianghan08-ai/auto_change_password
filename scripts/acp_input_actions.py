from __future__ import annotations

import time

from acp_common import info, warn
from acp_windowing import switch_to_english_input_method


def click_box(pyautogui, box: Box, label: str) -> tuple[int, int]:
    x, y = box.center
    info(f"点击并聚焦 {label}：x={x}, y={y}")
    pyautogui.click(x, y)
    time.sleep(0.12)
    pyautogui.click(x, y)
    time.sleep(0.25)
    return x, y

def focus_input_point(pyautogui, point: tuple[int, int], *, label: str) -> None:
    """Click the target point again immediately before keyboard operations.

    Some browsers briefly steal or delay focus after SetForegroundWindow/click.
    Re-clicking here makes the following Ctrl+A/typing act on the intended field
    instead of the page, address bar, or previous focused control.
    """
    x, y = point
    info(f"确认聚焦 {label}：x={x}, y={y}")
    pyautogui.click(x, y)
    time.sleep(0.2)

def focus_next_field_with_tab(pyautogui, *, label: str) -> None:
    """Move focus to the next field using normal form tab order."""
    info(f"按 Tab 切换焦点到 {label}")
    pyautogui.press("tab")
    time.sleep(0.25)

def type_text_fallback(pyautogui, text: str, *, label: str) -> None:
    info(f"使用键盘逐字符输入：{label}")
    try:
        pyautogui.write(text, interval=0.03)
    except Exception as exc:
        warn(f"逐字符输入 {label} 失败：{exc}")

def copy_focused_text(pyperclip, pyautogui, *, label: str) -> str | None:
    old_clipboard = None
    had_clipboard = True
    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        had_clipboard = False

    try:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.08)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.12)
        copied = pyperclip.paste()
        return copied
    except Exception as exc:
        warn(f"读取 {label} 输入框内容失败：{exc}")
        return None
    finally:
        try:
            if had_clipboard:
                pyperclip.copy(old_clipboard or "")
            else:
                pyperclip.copy("")
        except Exception:
            warn("剪贴板恢复失败，请检查剪贴板内容。")

def verify_account_text(pyautogui, pyperclip, expected: str) -> bool:
    copied = copy_focused_text(pyperclip, pyautogui, label="账号")
    if copied == expected:
        info("账号输入校验成功。")
        return True
    warn("账号输入校验失败，将清空后使用逐字符键入兜底。")
    return False

def clear_focused_text(pyautogui, *, label: str) -> None:
    info(f"清空 {label} 输入框")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.08)
    pyautogui.press("backspace")
    time.sleep(0.12)

def desktop_set_text_at_point(win32con, win32gui, x: int, y: int, text: str, *, label: str) -> bool:
    """Try system-level text injection for traditional Win32 controls."""
    try:
        hwnd = win32gui.WindowFromPoint((x, y))
        if not hwnd:
            return False
        class_name = win32gui.GetClassName(hwnd)
        if "edit" not in class_name.lower():
            warn(f"{label} 命中的桌面控件不是标准 Edit/RichEdit（class={class_name}），改用键盘逐字符输入。")
            return False
        win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, 0, "")
        time.sleep(0.08)
        win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, 0, text)
        time.sleep(0.2)

        if label == "账号":
            written = win32gui.GetWindowText(hwnd)
            if written != text:
                warn(
                    f"win32gui 写入账号后读回不一致，改用键盘逐字符输入。"
                    f" class={class_name}, read_back={written!r}"
                )
                return False

        info(f"已通过 win32gui 写入 {label}（class={class_name}）。")
        return True
    except Exception as exc:
        warn(f"win32gui 写入 {label} 失败，将回退到键盘逐字符输入：{exc}")
        return False

def input_text(
    pyautogui,
    pyperclip,
    win32con,
    win32gui,
    target: str,
    point: tuple[int, int],
    text: str,
    *,
    label: str,
    focus_before_input: bool = True,
) -> None:
    switch_to_english_input_method(win32gui)
    if target == "desktop":
        if desktop_set_text_at_point(win32con, win32gui, point[0], point[1], text, label=label):
            return

    if focus_before_input:
        focus_input_point(pyautogui, point, label=label)
    else:
        info(f"{label} 已通过键盘焦点切换，不再点击模板坐标。")
    clear_focused_text(pyautogui, label=label)
    type_text_fallback(pyautogui, text, label=label)
    if label == "账号" and not verify_account_text(pyautogui, pyperclip, text):
        focus_input_point(pyautogui, point, label=label)
        clear_focused_text(pyautogui, label=label)
        type_text_fallback(pyautogui, text, label=label)
        verify_account_text(pyautogui, pyperclip, text)
