import unittest

from utils.patch_krx_data_client import PATCH_MARKER, patch_source


SOURCE_FIXTURE = '''
async def _login_async_krx(self):
            await login_btn.click()
            logger.info("login clicked")
            await asyncio.sleep(3)

            home_url = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
            js_cookies_str = await page.evaluate("document.cookie")
            logger.info(f"[try {retry+1}/{max_cookie_retries}] JavaScript cookies: {js_cookies_str}")
'''


class PatchKrxDataClientTests(unittest.TestCase):
    def test_adds_modal_handling_and_masks_cookie_values(self):
        patched = patch_source(SOURCE_FIXTURE)

        self.assertIn(PATCH_MARKER, patched)
        self.assertIn("JavaScript cookie names", patched)
        self.assertNotIn("JavaScript cookies: {js_cookies_str}", patched)

    def test_is_idempotent(self):
        patched = patch_source(SOURCE_FIXTURE)

        self.assertEqual(patch_source(patched), patched)

    def test_fails_when_login_anchor_changes(self):
        with self.assertRaisesRegex(RuntimeError, "login button anchor"):
            patch_source(SOURCE_FIXTURE.replace("await login_btn.click()", "await changed.click()"))


if __name__ == "__main__":
    unittest.main()
