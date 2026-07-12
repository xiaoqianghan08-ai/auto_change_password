#!/usr/bin/env python3
"""Core workflow for Windows password-entry automation.

The reusable helpers live in acp_* modules next to this file. This module keeps
CLI orchestration and the high-level run loop.
"""

from __future__ import annotations

import argparse
import time

from acp_assets import collect_assets, iter_asset_app_names, print_asset_request, read_web_url_entries
from acp_common import fail, info, warn
from acp_debug import print_debug_guidance
from acp_environment import ensure_python_dependencies, import_gui_dependencies, is_admin, is_windows
from acp_input_actions import click_box, focus_next_field_with_tab, input_text
from acp_save_prompt import handle_save_update_password_prompt
from acp_vision import (
    infer_login_window_from_elements,
    locate_account_box,
    locate_password_box,
    locate_with_retries,
    require_locate,
)
from acp_windowing import (
    bring_window_to_front,
    close_application_windows,
    close_foreground_window,
    infer_target_type,
    launch_application,
    open_web_url,
    switch_to_chinese_input_method,
    switch_to_english_input_method,
    wait_for_window_to_front,
)


def prompt_missing(value: str | None, prompt: str) -> str:
    if value:
        return value
    return input(prompt)

def prompt_yes_no(prompt: str, *, default: bool | None = None) -> bool:
    while True:
        suffix = "y/n"
        if default is True:
            suffix = "Y/n"
        elif default is False:
            suffix = "y/N"
        answer = input(f"{prompt}（{suffix}）：").replace("\ufeff", "").strip().lower()
        if not answer and default is not None:
            return default
        if answer in {"y", "yes", "是", "退出", "q", "quit"}:
            return True
        if answer in {"n", "no", "否", "不", "不退出"}:
            return False
        print("请输入 y 或 n。")

def click_optional_left_side(
    pyautogui,
    image_path,
    label: str,
    *,
    login_window,
    confidence: float,
    attempts: int,
    retry_wait: float,
) -> bool:
    if not image_path.exists():
        return False

    box, score = locate_with_retries(
        pyautogui,
        image_path,
        region=login_window,
        confidence=confidence,
        min_confidence=0.68,
        attempts=attempts,
        retry_wait=retry_wait,
    )
    if not box and login_window is not None:
        box, score = locate_with_retries(
            pyautogui,
            image_path,
            confidence=confidence,
            min_confidence=0.68,
            attempts=attempts,
            retry_wait=retry_wait,
        )
    if not box:
        warn(f"未识别到可选点击项 {label}：{image_path.name}，跳过。")
        return False

    x = box.left + max(2, min(8, box.width // 10))
    y = box.top + box.height // 2
    pyautogui.click(x, y)
    info(f"点击可选项 {label} 最左侧：x={x}, y={y}, confidence={score}")
    time.sleep(0.25)
    return True

def ensure_target_window_ready(app_name: str, target: str, win32con, win32gui, *, after_focus_wait: float) -> None:
    if target == "desktop":
        if not wait_for_window_to_front(app_name, "desktop", win32con, win32gui, timeout=1.5):
            info(f"未发现可前置的 {app_name} 窗口，先尝试启动应用。")
            launch_application(app_name)
            if not wait_for_window_to_front(app_name, "desktop", win32con, win32gui, timeout=10.0):
                warn(f"未能自动前置 {app_name} 窗口，将继续使用当前前台窗口。请确认 {app_name} 已打开并停留在登录页面。")
    else:
        bring_window_to_front(app_name, target, win32con, win32gui)

    info(f"窗口已请求前置，等待 {after_focus_wait:.1f} 秒让目标应用/页面完成前置和重绘。")
    time.sleep(max(0.0, after_focus_wait))

def run_login_flow(
    args: argparse.Namespace,
    *,
    pyautogui,
    pyperclip,
    win32con,
    win32gui,
    app_name: str,
    account: str,
    password: str,
    asset_group: str | None = None,
    ask_confirmation: bool = True,
) -> int:
    target = args.target
    if target == "auto":
        target = infer_target_type(app_name)
    if target not in {"web", "desktop"}:
        fail("--target 只支持 web、desktop 或 auto。")

    args.app = app_name
    args.account = account
    args.password = password
    args.target = target

    app_dir, paths, missing_required, missing_optional = collect_assets(app_name, asset_group=asset_group)
    if asset_group:
        info(f"当前 web 地址使用资源目录：{app_dir}")
        if missing_required:
            fallback_app_dir, fallback_paths, fallback_missing_required, fallback_missing_optional = collect_assets(app_name)
            if not fallback_missing_required:
                warn(f"资源目录 {app_dir} 缺少必需图片，将回退使用应用根目录资源：{fallback_app_dir}")
                app_dir = fallback_app_dir
                paths = fallback_paths
                missing_required = fallback_missing_required
                missing_optional = fallback_missing_optional
    if missing_required:
        print_asset_request(app_name, app_dir, missing_required, missing_optional)
        return 2

    if missing_optional:
        warn("辅助/建议图片不完整；基础登录仍会继续，保存/更新密码提示将使用已提供的图片尽量识别。")
        for name in missing_optional:
            warn(f"缺失可选图片：{name}")

    info("请确保目标登录页面已经打开。3 秒后开始识别。")
    time.sleep(3)
    ensure_target_window_ready(app_name, target, win32con, win32gui, after_focus_wait=args.after_focus_wait)
    switch_to_english_input_method(win32gui)

    confidence = args.confidence
    login_window, window_confidence = locate_with_retries(
        pyautogui,
        paths["input_password_window"],
        confidence=confidence,
        min_confidence=0.62,
        attempts=args.recognition_retries,
        retry_wait=args.recognition_retry_wait,
    )

    if login_window:
        if window_confidence is not None and window_confidence < confidence:
            warn(f"账号密码输入窗口使用较低置信度识别成功：{window_confidence}")
        info(
            "识别到 账号密码输入窗口："
            f"left={login_window.left}, top={login_window.top}, "
            f"width={login_window.width}, height={login_window.height}"
        )
        login_button, _ = locate_with_retries(
            pyautogui,
            paths["login_button"],
            region=login_window,
            confidence=confidence,
            min_confidence=confidence,
            attempts=args.recognition_retries,
            retry_wait=args.recognition_retry_wait,
        )
        if login_button:
            info(
                "识别到 登录按钮："
                f"left={login_button.left}, top={login_button.top}, "
                f"width={login_button.width}, height={login_button.height}"
            )
        else:
            warn("已识别窗口内未找到登录按钮，窗口匹配可能不准确，将改用全屏子元素识别。")
            login_window = None

    if not login_window:
        warn("未识别到账号密码输入窗口模板，将改用子元素识别和布局反推。")
        login_button = require_locate(
            pyautogui,
            paths["login_button"],
            "登录按钮",
            confidence=confidence,
            app_name=app_name,
            attempts=args.recognition_retries,
            retry_wait=args.recognition_retry_wait,
        )
        account_template_box, account_template_confidence = locate_with_retries(
            pyautogui,
            paths["input_account"],
            confidence=confidence,
            min_confidence=0.68,
            attempts=args.recognition_retries,
            retry_wait=args.recognition_retry_wait,
        )
        password_template_box, password_template_confidence = locate_with_retries(
            pyautogui,
            paths["input_password"],
            confidence=confidence,
            min_confidence=0.68,
            attempts=args.recognition_retries,
            retry_wait=args.recognition_retry_wait,
        )
        if account_template_box:
            info(
                "全屏识别到账号输入框辅助模板："
                f"left={account_template_box.left}, top={account_template_box.top}, "
                f"width={account_template_box.width}, height={account_template_box.height}, "
                f"confidence={account_template_confidence}"
            )
        if password_template_box:
            info(
                "全屏识别到密码输入框辅助模板："
                f"left={password_template_box.left}, top={password_template_box.top}, "
                f"width={password_template_box.width}, height={password_template_box.height}, "
                f"confidence={password_template_confidence}"
            )
        login_window = infer_login_window_from_elements(
            pyautogui,
            login_button=login_button,
            account_box=account_template_box,
            password_box=password_template_box,
        )

    password_box = locate_password_box(
        pyautogui,
        paths["input_password"],
        login_window=login_window,
        login_button=login_button,
        confidence=confidence,
        attempts=args.recognition_retries,
        retry_wait=args.recognition_retry_wait,
    )
    account_box = locate_account_box(
        pyautogui,
        paths["input_account"],
        login_window=login_window,
        password_box=password_box,
        login_button=login_button,
        confidence=confidence,
        attempts=args.recognition_retries,
        retry_wait=args.recognition_retry_wait,
    )

    account_point = click_box(pyautogui, account_box, "账号输入框")
    input_text(pyautogui, pyperclip, win32con, win32gui, target, account_point, account, label="账号")
    if target == "web":
        password_point = password_box.center
        focus_next_field_with_tab(pyautogui, label="密码输入框")
        password_focus_before_input = False
    else:
        password_point = click_box(pyautogui, password_box, "密码输入框")
        password_focus_before_input = True
    input_text(
        pyautogui,
        pyperclip,
        win32con,
        win32gui,
        target,
        password_point,
        password,
        label="密码",
        focus_before_input=password_focus_before_input,
    )
    click_optional_left_side(
        pyautogui,
        paths["remember_password"],
        "记住密码",
        login_window=login_window,
        confidence=confidence,
        attempts=args.recognition_retries,
        retry_wait=args.recognition_retry_wait,
    )
    click_optional_left_side(
        pyautogui,
        paths["agree_protocol"],
        "同意协议",
        login_window=login_window,
        confidence=confidence,
        attempts=args.recognition_retries,
        retry_wait=args.recognition_retry_wait,
    )
    click_box(pyautogui, login_button, "登录按钮")
    switch_to_chinese_input_method(win32gui)

    handle_save_update_password_prompt(
        pyautogui,
        paths,
        app_name=app_name,
        confidence=confidence,
        initial_wait=args.post_login_wait,
        timeout=args.save_prompt_timeout,
        retry_wait=args.save_prompt_retry_wait,
    )

    if not ask_confirmation:
        info("流程完成。")
        return 0

    answer = input("账号密码是否输入成功？输入 y/n 后回车：").strip().lower()
    if answer in {"n", "no", "否", "失败"}:
        print_debug_guidance(app_name, confidence)
        return 3

    info("流程完成。")
    return 0

def prepare_runtime():
    if not is_windows():
        fail("此 skill 仅支持 Windows 桌面环境。")

    ensure_python_dependencies()

    if not is_admin():
        fail("当前不是管理员权限。请右键 run.bat，选择“以管理员身份运行”。")

    pyautogui, pyperclip, win32con, win32gui = import_gui_dependencies()
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.12
    return pyautogui, pyperclip, win32con, win32gui

def run_once(args: argparse.Namespace) -> int:
    pyautogui, pyperclip, win32con, win32gui = prepare_runtime()

    app_name = prompt_missing(args.app, "请输入需要自动修改密码的应用名称（例如 chrome）：").strip()
    account = prompt_missing(args.account, "请输入账号：")
    password = prompt_missing(args.password, "请输入密码：")

    return run_login_flow(
        args,
        pyautogui=pyautogui,
        pyperclip=pyperclip,
        win32con=win32con,
        win32gui=win32gui,
        app_name=app_name,
        account=account,
        password=password,
        ask_confirmation=True,
    )

def make_run_args(base_args: argparse.Namespace, *, app_name: str, account: str, password: str, target: str) -> argparse.Namespace:
    run_args = argparse.Namespace(**vars(base_args))
    run_args.app = app_name
    run_args.account = account
    run_args.password = password
    run_args.target = target
    return run_args

def run_batch_automation(args: argparse.Namespace) -> int:
    pyautogui, pyperclip, win32con, win32gui = prepare_runtime()
    account = prompt_missing(args.account, "请输入账号：")
    password = prompt_missing(args.password, "请输入密码：")

    app_names = iter_asset_app_names()
    if not app_names:
        warn("assets 目录下没有应用图片文件夹，无法批量执行。")
        return 2

    last_code = 0
    for app_name in app_names:
        target = infer_target_type(app_name)
        info(f"开始批量处理应用：{app_name}（{target}）")

        if target == "web":
            url_entries = read_web_url_entries(app_name)
            if not url_entries:
                warn(f"{app_name} 是 web 应用，但未找到或未配置 webUrl.txt，跳过。")
                last_code = last_code or 2
                continue

            for index, entry in enumerate(url_entries, start=1):
                info(
                    f"开始处理 {app_name} 第 {index}/{len(url_entries)} 个地址：{entry.url}；"
                    f"图片资源目录编号：{entry.asset_group}"
                )
                close_application_windows(app_name, "web", win32con, win32gui)
                time.sleep(1.0)
                open_web_url(app_name, entry.url)
                run_args = make_run_args(args, app_name=app_name, account=account, password=password, target="web")
                try:
                    code = run_login_flow(
                        run_args,
                        pyautogui=pyautogui,
                        pyperclip=pyperclip,
                        win32con=win32con,
                        win32gui=win32gui,
                        app_name=app_name,
                        account=account,
                        password=password,
                        asset_group=entry.asset_group,
                        ask_confirmation=False,
                    )
                    last_code = last_code or code
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
                    warn(f"{app_name} 地址执行失败，退出码：{code}")
                    last_code = last_code or code
                except Exception as exc:
                    warn(f"{app_name} 地址执行异常：{exc}")
                    last_code = last_code or 1
                finally:
                    close_foreground_window(pyautogui, label=f"{app_name} - {entry.url}")
        else:
            run_args = make_run_args(args, app_name=app_name, account=account, password=password, target="desktop")
            try:
                code = run_login_flow(
                    run_args,
                    pyautogui=pyautogui,
                    pyperclip=pyperclip,
                    win32con=win32con,
                    win32gui=win32gui,
                    app_name=app_name,
                    account=account,
                    password=password,
                    ask_confirmation=False,
                )
                last_code = last_code or code
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                warn(f"{app_name} 执行失败，退出码：{code}")
                last_code = last_code or code
            except Exception as exc:
                warn(f"{app_name} 执行异常：{exc}")
                last_code = last_code or 1

    info("批量自动修改流程完成。")
    return last_code

def ask_next_cycle_args(previous_args: argparse.Namespace) -> argparse.Namespace | None:
    should_exit = prompt_yes_no("是否退出自动输入密码工具", default=True)
    if should_exit:
        return None

    app_name = input("请输入需要自动修改密码的应用名称（例如 chrome）：").strip()
    while not app_name:
        app_name = input("应用名称不能为空，请重新输入：").strip()

    account = previous_args.account
    password = previous_args.password
    should_update_credentials = prompt_yes_no("是否需要更新账号密码", default=True)
    if not should_update_credentials and account and password:
        info("已选择不更新账号密码，将复用上一轮账号密码。")
    elif not should_update_credentials:
        warn("上一轮账号或密码为空，仍需要重新输入。")

    if should_update_credentials or not account:
        account = input("请输入账号：")
    if should_update_credentials or not password:
        password = input("请输入密码：")

    next_args = argparse.Namespace(**vars(previous_args))
    next_args.app = app_name
    next_args.account = account
    next_args.password = password
    next_args.target = "auto"
    return next_args

def run_single_application_loop(args: argparse.Namespace, last_code: int = 0) -> int:
    current_args = args

    while True:
        try:
            last_code = run_once(current_args)
        except SystemExit as exc:
            code = exc.code
            last_code = code if isinstance(code, int) else 1
        except Exception as exc:
            warn(f"本轮执行发生异常：{exc}")
            last_code = 1

        next_args = ask_next_cycle_args(current_args)
        if next_args is None:
            return last_code
        current_args = next_args

def run_loop(args: argparse.Namespace) -> int:
    print("自动输入密码工具运行中")
    last_code = 0

    print("[RISK] 批量自动修改会在处理 web 端应用前关闭对应浏览器窗口。")
    print("[RISK] 请提前保存 web 端应用中的未保存内容，避免数据丢失。")
    if prompt_yes_no("是否让工具自动修改应用的账号密码", default=False):
        while True:
            last_code = run_batch_automation(args)
            if prompt_yes_no("是否继续进行批量自动修改", default=False):
                continue
            if prompt_yes_no("是否退出当前工具", default=True):
                return last_code
            break

    return run_single_application_loop(args, last_code)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用模板图片自动输入账号密码，并可处理保存/更新密码提示。",
    )
    parser.add_argument("--app", help="应用名称，对应 assets/<应用名称>/ 文件夹。")
    parser.add_argument("--account", help="要输入的账号。")
    parser.add_argument("--password", help="要输入的密码；不传则在命令行明文提示输入。")
    parser.add_argument(
        "--target",
        choices=["auto", "web", "desktop"],
        default="auto",
        help="目标类型。auto 根据应用名称自动判断；浏览器类应用走 web，其它走 desktop。可手动指定 web 或 desktop。",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.86,
        help="图片匹配置信度，默认 0.86。",
    )
    parser.add_argument(
        "--post-login-wait",
        type=float,
        default=2.0,
        help="登录后等待保存/更新密码提示出现的秒数。",
    )
    parser.add_argument(
        "--save-prompt-timeout",
        type=float,
        default=10.0,
        help="登录后持续搜索保存/更新密码提示的最长秒数，默认 10。",
    )
    parser.add_argument(
        "--save-prompt-retry-wait",
        type=float,
        default=0.5,
        help="保存/更新密码提示每轮识别失败后的等待秒数，默认 0.5。",
    )
    parser.add_argument(
        "--after-focus-wait",
        type=float,
        default=1.5,
        help="窗口前置后等待页面完成激活和重绘的秒数，默认 1.5。",
    )
    parser.add_argument(
        "--recognition-retries",
        type=int,
        default=2,
        help="关键图片识别总轮数，默认 2。",
    )
    parser.add_argument(
        "--recognition-retry-wait",
        type=float,
        default=1.0,
        help="关键图片识别失败后，下一轮重新截图识别前等待的秒数，默认 1.0。",
    )
    return parser

def main() -> int:
    try:
        return run_loop(build_parser().parse_args())
    except KeyboardInterrupt:
        print()
        warn("用户中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
