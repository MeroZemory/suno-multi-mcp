"""Authentication tools for Suno MCP — Google OAuth via Clerk."""

import asyncio
import logging
import sys

from ..browser.manager import BrowserManager
from ..browser.navigator import find_visible, navigate_to, try_click, try_fill
from ..exceptions import AuthError

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)

SUNO_HOME = "https://suno.com"


class AuthTools:
    """Handles Suno AI authentication via Google OAuth."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def login(self, email: str, password: str) -> str:
        """Login to Suno AI via Google OAuth. Saves session on success."""
        try:
            components = await self.manager.ensure_browser(headless=False)
            page = components["page"]

            # Check if already logged in
            if await self._is_logged_in(page):
                return "✅ Already logged in. Session is active."

            # Navigate to suno.com
            await navigate_to(page, SUNO_HOME)
            await asyncio.sleep(1)

            # Click "Sign In" button
            sign_in_selectors = [
                'button:has-text("Sign In")',
                'button:has-text("Sign in")',
                'a:has-text("Sign In")',
                'a:has-text("Sign in")',
                '[data-testid="sign-in-button"]',
            ]
            clicked = await try_click(page, sign_in_selectors, timeout=5_000)
            if not clicked:
                raise AuthError("Sign In button not found", "SIGNIN_BUTTON_NOT_FOUND")

            # Wait for Google button to appear (poll up to 8 seconds)
            google_sel = await find_visible(
                page,
                [
                    'button:has-text("Continue with Google")',
                    'button:has-text("Google")',
                    '[data-provider="google"]',
                    'a:has-text("Continue with Google")',
                ],
                timeout=8_000,
            )
            if not google_sel:
                raise AuthError("Google login button not found", "GOOGLE_BUTTON_NOT_FOUND")

            # Click Google button
            await try_click(page, [google_sel], timeout=5_000)

            # Wait for redirect to Google accounts
            try:
                await page.wait_for_url("**/accounts.google.com/**", timeout=10_000)
            except Exception:
                # May have opened a new tab or popup — handle both
                pass

            # Handle Google OAuth form
            await self._handle_google_oauth(page, email, password)

            # Wait for return to suno.com
            try:
                await page.wait_for_url("**/suno.com/**", timeout=30_000)
            except Exception:
                await asyncio.sleep(3)

            if not await self._is_logged_in(page):
                raise AuthError(
                    "Login failed — still not authenticated after OAuth flow",
                    "LOGIN_FAILED",
                )

            # Save session for future use
            await self.manager.save_session()
            final_url = page.url
            return f"✅ Login successful!\nCurrent URL: {final_url}\nSession saved for future use."

        except AuthError:
            raise
        except Exception as e:
            logger.error("Login failed: %s", e)
            raise AuthError(f"Login failed: {e}", "LOGIN_ERROR")

    async def _handle_google_oauth(self, page: object, email: str, password: str) -> None:
        """Fill Google OAuth email and password forms."""
        from playwright.async_api import Page
        assert isinstance(page, Page)

        await asyncio.sleep(1)

        # Email step
        email_selectors = [
            'input[type="email"]',
            'input[name="identifier"]',
            '#identifierInput',
            '#Email',
        ]
        filled = await try_fill(page, email_selectors, email, timeout=5_000)
        if not filled:
            raise AuthError("Google email field not found", "GOOGLE_EMAIL_NOT_FOUND")

        # Click Next after email
        await try_click(
            page,
            ['#identifierNext', 'button:has-text("Next")', 'input[value="Next"]'],
            timeout=5_000,
        )
        await asyncio.sleep(1)

        # Password step
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            '#passwordInput',
            '#Passwd',
        ]
        filled = await try_fill(page, password_selectors, password, timeout=8_000)
        if not filled:
            raise AuthError("Google password field not found", "GOOGLE_PASSWORD_NOT_FOUND")

        # Click Next after password
        await try_click(
            page,
            ['#passwordNext', 'button:has-text("Next")', 'input[value="Next"]'],
            timeout=5_000,
        )

    async def _is_logged_in(self, page: object) -> bool:
        """Check if the user is currently logged in to Suno."""
        from playwright.async_api import Page
        assert isinstance(page, Page)
        try:
            url = page.url or ""
            if "suno.com" not in url:
                return False
            # Look for user avatar or account menu (visible when logged in)
            logged_in_sel = await find_visible(
                page,
                [
                    '[data-testid="user-avatar"]',
                    '[data-testid="account-menu"]',
                    'button[aria-label*="account" i]',
                    'img[alt*="avatar" i]',
                    'a[href="/me"]',
                    'a[href*="/profile"]',
                ],
                timeout=3_000,
            )
            return logged_in_sel is not None
        except Exception:
            return False
