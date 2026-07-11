#!/usr/bin/env python3
"""Entry point for the auto-change-password runner.

The implementation lives in `auto_change_password_core.py`. Keeping this file
small preserves the existing run.bat/CLI entry path while making the main entry
module easy to read.
"""

from __future__ import annotations

from auto_change_password_core import main


if __name__ == "__main__":
    raise SystemExit(main())
