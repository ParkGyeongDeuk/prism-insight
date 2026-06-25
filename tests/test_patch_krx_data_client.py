import unittest

from utils.patch_krx_data_client import (
    LOGOUT_PATCH_MARKER,
    NAVIGATION_PATCH_MARKER,
    PATCH_MARKER,
    patch_source,
)


SOURCE_FIXTURE = '''
async def _login_async_krx(self):
            logout_url = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D2.cmd"
            logger.info(f"기존 세션 정리를 위해 로그아웃 수행: {logout_url}")
            await page.goto(logout_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(10)  # KRX 서버에서 세션 정리 시간 확보 (충분히 대기)

            login_url = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
            await page.goto(login_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(2)

            await login_btn.click()
            logger.info("login clicked")
            await asyncio.sleep(3)

            home_url = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
            await page.goto(home_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)

            data_page_url = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201010105"
            await page.goto(data_page_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)

            js_cookies_str = await page.evaluate("document.cookie")
            logger.info(f"[try {retry+1}/{max_cookie_retries}] JavaScript cookies: {js_cookies_str}")
'''


class PatchKrxDataClientTests(unittest.TestCase):
    def test_adds_modal_handling_and_masks_cookie_values(self):
        patched = patch_source(SOURCE_FIXTURE)

        self.assertIn(PATCH_MARKER, patched)
        self.assertIn(LOGOUT_PATCH_MARKER, patched)
        self.assertIn(NAVIGATION_PATCH_MARKER, patched)
        self.assertIn('wait_until="domcontentloaded", timeout=30000', patched)
        self.assertNotIn('wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT', patched)
        self.assertEqual(patched.count('wait_until="domcontentloaded"'), 4)
        self.assertIn("JavaScript cookie names", patched)
        self.assertNotIn("JavaScript cookies: {js_cookies_str}", patched)

    def test_is_idempotent(self):
        patched = patch_source(SOURCE_FIXTURE)

        self.assertEqual(patch_source(patched), patched)

    def test_patches_remaining_navigation_when_marker_already_exists(self):
        source = SOURCE_FIXTURE.replace(
            '            await page.goto(login_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)\n',
            (
                f"            # {NAVIGATION_PATCH_MARKER}\n"
                '            await page.goto(login_url, wait_until="domcontentloaded", timeout=self.PAGE_LOAD_TIMEOUT)\n'
                '            await page.goto(login_url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)\n'
            ),
            1,
        )

        patched = patch_source(source)

        self.assertNotIn('wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT', patched)

    def test_fails_when_login_anchor_changes(self):
        with self.assertRaisesRegex(RuntimeError, "login button anchor"):
            patch_source(SOURCE_FIXTURE.replace("await login_btn.click()", "await changed.click()"))

    def test_fails_when_logout_anchor_changes(self):
        with self.assertRaisesRegex(RuntimeError, "logout cleanup anchor"):
            patch_source(SOURCE_FIXTURE.replace("await page.goto(logout_url", "await page.goto(changed_url"))


if __name__ == "__main__":
    unittest.main()
