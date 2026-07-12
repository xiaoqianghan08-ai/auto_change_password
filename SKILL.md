---
name: auto-change-password
description: Automate password entry/update for Windows applications or web login pages using user-provided account, password, application name, and image templates. Use when the user says “自动修改密码”, asks to run run.bat as administrator, or needs a Windows skill that locates login/save-password UI elements from the assets application-name folder and types credentials safely.
---

# Auto Change Password

## Purpose

Use this skill to automate typing a user-provided account and password into a Windows desktop application or a web login page, then optionally click save/update-password prompts if template images are available.

The bundled runner is `run.bat`; the CLI entry point is `scripts/auto_change_password.py`, the high-level workflow is in `scripts/auto_change_password_core.py`, and the debug helper is `scripts/debug_tool.py`.

Implementation modules under `scripts/`:

- `acp_common.py`: shared constants, `Box`, logging, and skill path helpers.
- `acp_environment.py`: dependency checks, Windows/admin checks, and GUI imports.
- `acp_assets.py`: asset folder scanning and missing-image guidance.
- `acp_windowing.py`: target type inference, window foregrounding, and English keyboard layout switching.
- `acp_vision.py`: template matching, multi-scale matching, and login-field geometry inference.
- `acp_input_actions.py`: clicking, focusing, clearing, keyboard typing, and desktop-control fallback.
- `acp_save_prompt.py`: Chrome save/update-password prompt recognition and clicking.
- `acp_debug.py`: debug guidance and automatic `debug_tool.py` execution.

## Trigger workflow

1. Trigger this skill when the user enters `自动修改密码` or explicitly asks to run this skill.
2. Ask the user for:
   - account
   - password; command-line input is visible and not hidden
   - application name, such as `chrome` or `QQ`
   - target type only if the user wants to override automatic detection
3. Prefer running `run.bat` with administrator privileges. If it is not elevated, tell the user to rerun it as administrator.

## Asset layout

Store template images under:

```text
assets/<应用名称>/
```

Required images:

```text
<应用名称>_login_button.png
```

Context and field templates. Provide these if possible, but they are not required for the basic flow:

```text
<应用名称>_input_password_window.png
<应用名称>_input_account.png
<应用名称>_input_password.png
```

For `<应用名称>_input_account.png` and `<应用名称>_input_password.png`, capture the full input box body rather than only a label or icon. When these templates are recognized, the runner clicks the template center directly. Layout inference is only a fallback when the field template is missing or not recognized.

Recommended optional save/update images:

```text
<应用名称>_save_password_window.png
<应用名称>_save_password.png
<应用名称>_update_password.png
```

Optional pre-login click images. If present, the runner clicks the left side of each image after account/password typing and before clicking the login button:

```text
<应用名称>_remember_password.png
<应用名称>_agree_protocol.png
```

For web applications, optionally add:

```text
assets/<应用名称>/webUrl.txt
```

Use one URL per line. Blank lines and lines starting with `#` are ignored. Each web URL can use its own image-resource folder under `assets/<应用名称>/`:

```text
assets/<应用名称>/webUrl.txt
1、http://localhost:8080/login
2、https://example.com/login
```

For the first line above, put that page's images in `assets/<应用名称>/1/`; for the second line, put them in `assets/<应用名称>/2/`. Inside these numbered folders, prefer short image names:

```text
input_password_window.png
input_account.png
input_password.png
login_button.png
remember_password.png
agree_protocol.png
save_password_window.png
save_password.png
update_password.png
```

The runner also accepts prefixed names such as `<应用名称>_input_account.png` inside the numbered folder. If a numbered folder is missing required images, the runner falls back to the original application root images in `assets/<应用名称>/`. If `webUrl.txt` contains only raw URLs without an explicit prefix number, the runner uses the non-empty URL order as the folder name (`1`, `2`, `3`, ...).

If the application folder or any required image is missing, request the missing images from the user. The runner prints the exact storage path, naming pattern, required filenames, optional filenames, and screenshot guidance in the cmd window.

For desktop applications that are not already open and cannot be found automatically, optionally add:

```text
assets/<应用名称>/appPath.txt
```

Put one launcher path or command on the first non-comment line, for example:

```text
C:\Program Files\Vendor\VDrive\vdrive.exe
```

The launcher can be an `.exe`, `.lnk`, or a command line. This is the recommended fallback for newly added desktop applications whose executable name or shortcut cannot be inferred from the asset folder name.

## Automation behavior

Run:

```powershell
.\run.bat
```

`run.bat` keeps the cmd window open after the Python script exits, prints the exit code, and lets the user read missing-asset or debug guidance before closing the window.

The first visible tool line is `自动输入密码工具运行中`. Before asking for batch mode, the Python tool prints a risk warning that web applications will be closed and the user should save unsaved web content first. It then asks whether to let the tool automatically modify account/passwords for applications. If the user answers yes, it asks once for account/password, then reads every application folder under `assets/` in sorted order:

- `web` applications: read `assets/<应用名称>/webUrl.txt`; before each URL, close existing windows for that browser application to avoid stale pages interfering with recognition, then reopen the browser with that URL, load that URL's images from the corresponding numbered/resource folder, type the supplied account/password, click save/update-password prompts when templates are available, close the current browser window, then continue with the next URL.
- `desktop` applications: first try to foreground an already-open window. If no matching window is found, resolve and start the application from `assets/<应用名称>/appPath.txt`, PATH, Windows App Paths registry, known install locations, Start Menu/Desktop shortcuts, or common installation directories, then wait and retry foreground activation before running the same image-recognition and typing flow.

Batch mode does not pause after every application to ask whether typing succeeded; use the printed logs and `debug_output` when recognition fails. After one full batch finishes, the Python tool asks whether to continue batch auto-modification. If the user answers `y`, it runs another full batch. If the user answers `n`, it asks whether to exit the current tool. If the user answers `y`, the tool exits; if the user answers `n`, it enters the original single-application loop. If the user answers no to batch mode at startup, the original single-application loop is used immediately: after each run, including missing-asset or recognition-failure runs, the Python tool asks whether to exit. If the user chooses not to exit, it asks for the next application name, asks whether to update account/password, then repeats the same password-entry flow.

or:

```powershell
python .\scripts\auto_change_password.py --app <应用名称> --account <账号> --password <密码>
```

The default `--target auto` detects browser-style application names such as `chrome`, `firefox`, `edge`, `brave`, `opera`, `QQ浏览器`, or names containing `browser`/`浏览器` as `web`; all other application names, such as `QQ`, run as `desktop`. Use `--target web` or `--target desktop` only to override this automatic choice.

Useful stability options:

```powershell
python .\scripts\auto_change_password.py --after-focus-wait 1.5 --recognition-retries 2 --recognition-retry-wait 1.0
python .\scripts\auto_change_password.py --save-prompt-timeout 10 --save-prompt-retry-wait 0.5
```

The script:

1. Checks Python dependencies before running; missing packages are installed automatically with the current Python interpreter.
2. If dependency installation fails, prints the missing packages and the manual `python -m pip install ...` command.
3. Confirms it is running on Windows with administrator privileges.
4. Finds `assets/<应用名称>/` and validates required images.
5. Infers the target type from the application name when `--target auto` is used, then brings the target application window to the foreground:
   - `desktop`: use `win32gui` window enumeration and activation; if no matching window is found, launch the application before image recognition. When launching, first read `assets/<应用名称>/appPath.txt`, then resolve executable names such as `QQ.exe`/`QQScLauncher.exe`, Windows App Paths registry entries, known install paths, Start Menu/Desktop shortcuts, and common installation directories instead of blindly running `start <应用名称>`.
   - `web`: prefer activating a browser window whose title contains the application name; if not found, continue with the current foreground window.
6. Waits after foreground activation (`--after-focus-wait`, default 1.5 seconds) so Chrome or the desktop app can finish repainting and focus changes, then requests the English US keyboard layout (`00000409`) for the foreground window. Before each account/password typing operation, request the English layout again so an active Chinese IME does not intercept `pyautogui.write()` into composition/candidate mode. After clicking the login button, request the Simplified Chinese keyboard layout (`00000804`) for the foreground window so the user's local input method returns to Chinese.
7. Tries `<应用名称>_input_password_window.png` as a context region, but do not fail if it is not recognized. Critical image recognition uses multiple screenshot rounds (`--recognition-retries`, default 2; `--recognition-retry-wait`, default 1.0 second) before falling back. If the context image fails, locate `<应用名称>_login_button.png`, `<应用名称>_input_account.png`, and `<应用名称>_input_password.png` globally, then infer the login window from those child elements. Use account/password templates as direct click targets whenever they are recognized; use inferred positions only when a field template is missing or not recognized.
8. Clicks the account field, then clicks the target point again immediately before `Ctrl+A`/typing to avoid stale focus after browser foreground changes. Clears the field with `Ctrl+A` plus `Backspace`, enters the account by keyboard character-by-character typing only, then verifies the account field by copying selected text back and retrying character typing if verification fails. For `web` targets, move from the account field to the password field with `Tab` and do not click the password template again before typing; this avoids pages where clicking the password container leaves focus in the account field. For `desktop` targets, use `WM_SETTEXT` only when the target point resolves to a standard Win32 `Edit`/`RichEdit` control and account read-back verifies the write; for custom/self-drawn controls such as QQ, fall back to focused keyboard character-by-character typing. Do not use `Ctrl+V` or clipboard paste for input.
9. Before clicking the login button, if `<应用名称>_remember_password.png` or `<应用名称>_agree_protocol.png` exists and is recognized, click the left side of the recognized image. These clicks are optional and skipped when the images are absent or not recognized.
10. If any save/update images exist, handles Chrome-style save/update password prompts with a separate robust flow. After login, wait `--post-login-wait`, then search for up to `--save-prompt-timeout` seconds, retrying every `--save-prompt-retry-wait` seconds. Search `<应用名称>_save_password_window.png` across the full desktop/window, not inside the login form region. Use lower confidence for the window (`min_confidence=0.65`), grayscale fallback, and OpenCV multi-scale fallback. Prefer clicking `<应用名称>_update_password.png`; if it is not found, click `<应用名称>_save_password.png`. Search buttons first inside the detected prompt window, then across the full screen. If the prompt/window/buttons still cannot be recognized, automatically run `debug_tool.py`.
11. Prompts the user to confirm whether the account and password were typed successfully after the typing flow completes. If the answer is `n`, `no`, `否`, or `失败`, it prints step-by-step `debug_tool.py` guidance.
12. Prompts whether to exit the tool. If the user chooses not to exit, ask for another application and whether to update account/password, then run another cycle. If the user answers `n` to updating account/password and the previous account/password exist, reuse the previous values and do not prompt for them again.

If the flow exits before this confirmation prompt, read the cmd output: it should show missing required assets, dependency installation failure, administrator-permission failure, or image-recognition failure. For image-recognition failure, the script asks the user to open the target page and bring it to the foreground, waits 5 seconds, runs `debug_tool.py` automatically, then prints the generated `desktop_screenshot.png`, `annotated_matches.png`, and `match_summary.json` paths.

## Debug workflow

If the user reports failure, run:

```powershell
python .\scripts\debug_tool.py --app <应用名称>
```

The debug tool writes:

- a full desktop screenshot
- annotated images showing where each provided template was detected; for below-threshold misses, it also marks the best candidate location with its score
- a JSON summary of found/missing templates, best match confidence, coordinates, scale, and grayscale mode

The debug tool also checks and installs its own Python dependencies before taking screenshots.

Do not print or persist the user's password in debug output. Password entry in the main runner is visible in the cmd window when prompted interactively.
