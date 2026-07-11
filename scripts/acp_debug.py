from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from acp_common import skill_dir, warn


def print_debug_guidance(app_name: str, confidence: float) -> None:
    debug_script = skill_dir() / "scripts" / "debug_tool.py"
    debug_command = f'python "{debug_script}" --app "{app_name}" --confidence {confidence}'
    print()
    print("[DEBUG] 如果账号密码没有输入成功，请按下面步骤调试：")
    print("  1. 保持目标应用/网页停留在账号密码输入界面。")
    print("  2. 在当前 skill 目录打开 cmd 或 PowerShell。")
    print("  3. 运行下面命令生成桌面截图、模板匹配标注图和 JSON 摘要：")
    print(f"     {debug_command}")
    print("  4. 查看 debug_output 目录中的 annotated_matches.png。")
    print("     如果标注框位置不对，请重新截取 assets 目录下对应图片。")
    print()

def run_debug_tool_automatically(app_name: str, confidence: float, reason: str) -> Path | None:
    output_dir = skill_dir() / "debug_output" / f"{app_name}_{time.strftime('%Y%m%d_%H%M%S')}"
    debug_script = skill_dir() / "scripts" / "debug_tool.py"

    print()
    print(f"[DEBUG] {reason}")
    print("[DEBUG] 即将自动执行 debug_tool.py。")
    print("[DEBUG] 请打开要识别的页面，并将目标窗口置于桌面最前。")
    print("[DEBUG] 5 秒后开始截图和模板匹配。")
    for remaining in range(5, 0, -1):
        print(f"[DEBUG] 倒计时 {remaining} 秒...")
        time.sleep(1)

    command = [
        sys.executable,
        str(debug_script),
        "--app",
        app_name,
        "--confidence",
        str(confidence),
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        warn(f"debug_tool.py 自动执行失败，退出码：{result.returncode}")
        print_debug_guidance(app_name, confidence)
        return None

    print()
    print("[DEBUG] debug_tool.py 已执行完成，输出文件位置：")
    print(f"  桌面截图：{output_dir / 'desktop_screenshot.png'}")
    print(f"  标注图片：{output_dir / 'annotated_matches.png'}")
    print(f"  匹配摘要：{output_dir / 'match_summary.json'}")
    print()
    return output_dir
