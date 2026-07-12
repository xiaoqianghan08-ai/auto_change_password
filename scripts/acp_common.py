from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_SUFFIXES = [
    "login_button",
]

CONTEXT_TEMPLATE_SUFFIXES = [
    "input_password_window",
]

FIELD_TEMPLATE_SUFFIXES = [
    "input_account",
    "input_password",
]

SAVE_OPTIONAL_SUFFIXES = [
    "save_password_window",
    "save_password",
    "update_password",
]

PRE_LOGIN_OPTIONAL_SUFFIXES = [
    "remember_password",
    "agree_protocol",
]

OPTIONAL_SUFFIXES = (
    CONTEXT_TEMPLATE_SUFFIXES
    + FIELD_TEMPLATE_SUFFIXES
    + PRE_LOGIN_OPTIONAL_SUFFIXES
    + SAVE_OPTIONAL_SUFFIXES
)
SAVE_PROMPT_SCALES = [1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15]


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def as_region(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)

def fail(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", flush=True)
    raise SystemExit(code)

def info(message: str) -> None:
    print(f"[INFO] {message}")

def warn(message: str) -> None:
    print(f"[WARN] {message}")

def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]

def image_name(app_name: str, suffix: str) -> str:
    return f"{app_name}_{suffix}.png"
