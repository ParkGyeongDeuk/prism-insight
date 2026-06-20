#!/usr/bin/env python3
"""Apply narrowly scoped compatibility fixes to krx_data_client."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PATCH_MARKER = "PRISM compatibility: confirm an existing KRX login session."
LOGIN_CLICK = "            await login_btn.click()\n"
LOGIN_HOME = (
    '            home_url = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"\n'
)
LOGIN_SLEEP = "            await asyncio.sleep(3)\n"

MODAL_PATCH = '''

            # PRISM compatibility: confirm an existing KRX login session.
            # KRX renders this prompt as a DOM modal, not a browser dialog.
            existing_session_confirmed = False
            for modal_scope in (frame, page):
                try:
                    confirm_buttons = modal_scope.get_by_text("확인", exact=True)
                    for index in range(await confirm_buttons.count() - 1, -1, -1):
                        candidate = confirm_buttons.nth(index)
                        if await candidate.is_visible():
                            await candidate.click()
                            logger.info("Existing KRX session confirmation modal accepted")
                            existing_session_confirmed = True
                            await asyncio.sleep(3)
                            break
                except Exception as modal_error:
                    logger.debug(f"Existing-session modal check skipped: {modal_error}")
                if existing_session_confirmed:
                    break
'''


def patch_source(source: str) -> str:
    """Return patched source, failing closed when upstream structure changes."""
    if PATCH_MARKER not in source:
        click_pos = source.find(LOGIN_CLICK)
        if click_pos < 0:
            raise RuntimeError("KRX login button anchor not found; review upstream changes")

        home_pos = source.find(LOGIN_HOME, click_pos)
        if home_pos < 0:
            raise RuntimeError("KRX login home anchor not found; review upstream changes")

        login_block = source[click_pos:home_pos]
        if "get_by_text(" in login_block or "existing_session" in login_block:
            raise RuntimeError("Upstream modal handling detected; review local patch")

        sleep_pos = source.find(LOGIN_SLEEP, click_pos, home_pos)
        if sleep_pos < 0:
            raise RuntimeError("KRX post-login wait anchor not found; review upstream changes")
        insert_pos = sleep_pos + len(LOGIN_SLEEP)
        source = source[:insert_pos] + MODAL_PATCH + source[insert_pos:]

    raw_cookie_lines = [
        line
        for line in source.splitlines()
        if "logger.info" in line
        and "JavaScript" in line
        and "js_cookies_str" in line
    ]
    safe_cookie_marker = "JavaScript cookie names"
    if safe_cookie_marker not in source:
        if len(raw_cookie_lines) != 1:
            raise RuntimeError("Raw KRX cookie log anchor changed; review upstream changes")
        raw_line = raw_cookie_lines[0]
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        safe_lines = (
            f'{indent}js_cookie_names = [\n'
            f'{indent}    item.split("=", 1)[0].strip()\n'
            f'{indent}    for item in js_cookies_str.split(";") if "=" in item\n'
            f'{indent}]\n'
            f'{indent}logger.info(\n'
            f'{indent}    f"[attempt {{retry+1}}/{{max_cookie_retries}}] "\n'
            f'{indent}    f"JavaScript cookie names: {{js_cookie_names}}"\n'
            f'{indent})'
        )
        source = source.replace(raw_line, safe_lines, 1)

    return source


def find_installed_module() -> Path:
    spec = importlib.util.find_spec("krx_data_client")
    if spec is None or spec.origin is None:
        raise RuntimeError("krx_data_client is not installed")
    return Path(spec.origin)


def main() -> None:
    module_path = find_installed_module()
    original = module_path.read_text(encoding="utf-8")
    patched = patch_source(original)
    if patched != original:
        module_path.write_text(patched, encoding="utf-8")
        print(f"Patched {module_path.name} for KRX login compatibility")
    else:
        print(f"KRX compatibility patch already applied to {module_path.name}")


if __name__ == "__main__":
    main()
