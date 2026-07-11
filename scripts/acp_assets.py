from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from acp_common import OPTIONAL_SUFFIXES, REQUIRED_SUFFIXES, image_name, skill_dir


@dataclass(frozen=True)
class WebUrlEntry:
    asset_group: str
    url: str
    display_index: int


def image_candidates(app_name: str, suffix: str, app_dir: Path, *, prefer_short_name: bool) -> list[Path]:
    short_name = app_dir / f"{suffix}.png"
    prefixed_name = app_dir / image_name(app_name, suffix)
    return [short_name, prefixed_name] if prefer_short_name else [prefixed_name, short_name]

def resolve_image_path(app_name: str, suffix: str, app_dir: Path, *, prefer_short_name: bool) -> Path:
    candidates = image_candidates(app_name, suffix, app_dir, prefer_short_name=prefer_short_name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

def collect_assets(app_name: str, asset_group: str | None = None) -> tuple[Path, dict[str, Path], list[str], list[str]]:
    app_dir = skill_dir() / "assets" / app_name
    if asset_group:
        app_dir = app_dir / asset_group
    prefer_short_name = asset_group is not None

    required = {
        suffix: resolve_image_path(app_name, suffix, app_dir, prefer_short_name=prefer_short_name)
        for suffix in REQUIRED_SUFFIXES
    }
    optional = {
        suffix: resolve_image_path(app_name, suffix, app_dir, prefer_short_name=prefer_short_name)
        for suffix in OPTIONAL_SUFFIXES
    }

    missing_required = [path.name for path in required.values() if not path.exists()]
    missing_optional = [path.name for path in optional.values() if not path.exists()]

    paths = {**required, **optional}
    return app_dir, paths, missing_required, missing_optional

def iter_asset_app_names() -> list[str]:
    assets_dir = skill_dir() / "assets"
    if not assets_dir.exists():
        return []
    return sorted(path.name for path in assets_dir.iterdir() if path.is_dir())

def parse_web_url_line(line: str, fallback_index: int) -> WebUrlEntry | None:
    line = line.strip().replace("\ufeff", "")
    if not line or line.startswith("#"):
        return None

    match = re.match(r"^([A-Za-z0-9_-]+)\s*(?:、|,|，|\||\t|\s+)\s*(https?://.+)$", line)
    if match:
        return WebUrlEntry(asset_group=match.group(1), url=match.group(2).strip(), display_index=fallback_index)

    return WebUrlEntry(asset_group=str(fallback_index), url=line, display_index=fallback_index)

def read_web_url_entries(app_name: str) -> list[WebUrlEntry]:
    url_file = skill_dir() / "assets" / app_name / "webUrl.txt"
    if not url_file.exists():
        return []
    entries: list[WebUrlEntry] = []
    for line in url_file.read_text(encoding="utf-8").splitlines():
        entry = parse_web_url_line(line, len(entries) + 1)
        if entry:
            entries.append(entry)
    return entries

def read_web_urls(app_name: str) -> list[str]:
    return [entry.url for entry in read_web_url_entries(app_name)]

def print_asset_request(app_name: str, app_dir: Path, missing_required: list[str], missing_optional: list[str]) -> None:
    print()
    print("[ASSET] 未检查到当前应用需要的图片资源，无法开始键入账号密码。")
    print()
    print(f"请创建/确认以下目录，并将截图图片放到该目录：")
    print(f"  {app_dir}")
    print()
    print("命名方式：")
    print(f"  必须图片：{app_name}_login_button.png")
    print(f"  上下文图片：{app_name}_input_password_window.png")
    print(f"  字段图片：{app_name}_input_account.png")
    print(f"  字段图片：{app_name}_input_password.png")
    print(f"  建议图片：{app_name}_save_password_window.png")
    print(f"  建议图片：{app_name}_save_password.png")
    print(f"  建议图片：{app_name}_update_password.png")
    print()
    if missing_required:
        print("必须提供的图片缺失：")
        for name in missing_required:
            print(f"  - {name}")
    if missing_optional:
        print("辅助/建议图片缺失（可选，不影响基础登录流程）：")
        for name in missing_optional:
            print(f"  - {name}")
    print()
    print("截图建议：")
    print("  - *_input_password_window.png 截取账号密码输入窗口或区域，用于圈定识别范围；识别失败时会用子元素反推范围。")
    print("  - *_input_account.png 截取完整账号输入框本体，用于直接点击模板中心；不要截输入内容。")
    print("  - *_input_password.png 截取完整密码输入框本体，用于直接点击模板中心；不要截输入内容。")
    print("  - *_login_button.png 只截取登录按钮。")
    print("  - 尽量不要包含账号、密码等敏感文字。")
