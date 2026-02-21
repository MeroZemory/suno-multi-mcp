"""Browser lifecycle management with stealth mode and session persistence."""

import logging
import sys
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ..exceptions import BrowserError
from ..session.store import SessionStore

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)


class BrowserManager:
    """Manages Playwright browser with stealth mode and session persistence."""

    def __init__(self, session_store: Optional[SessionStore] = None) -> None:
        self.session_store = session_store or SessionStore()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def ensure_browser(self, headless: bool = False) -> dict[str, Any]:
        """Initialize browser if not already running. Returns browser components."""
        try:
            if not self._playwright:
                self._playwright = await async_playwright().start()

            if not self._browser:
                self._browser = await self._playwright.chromium.launch(
                    channel="chrome",
                    headless=headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                )

            if not self._context:
                self._context = await self._create_context()

            if not self._page:
                self._page = await self._context.new_page()
                self._page.set_default_timeout(30_000)
                self._page.set_default_navigation_timeout(30_000)
                await self._apply_stealth(self._page)

            return {
                "playwright": self._playwright,
                "browser": self._browser,
                "context": self._context,
                "page": self._page,
            }
        except Exception as e:
            logger.error("Browser initialization failed: %s", e)
            raise BrowserError(f"Browser initialization failed: {e}", "BROWSER_INIT_ERROR")

    async def _create_context(self) -> BrowserContext:
        """Create browser context, restoring session if available."""
        assert self._browser is not None
        kwargs: dict[str, Any] = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "accept_downloads": True,
        }
        saved = self.session_store.load()
        if saved:
            kwargs["storage_state"] = saved
            logger.info("Restored browser session from storage")

        context = await self._browser.new_context(**kwargs)
        # Prevent automation detection via init script
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return context

    async def _apply_stealth(self, page: Page) -> None:
        """Apply playwright-stealth patches to evade bot detection."""
        try:
            from playwright_stealth import Stealth  # type: ignore[import]
            await Stealth().apply_stealth_async(page)
            logger.info("Stealth mode applied")
        except ImportError:
            logger.warning("playwright-stealth not installed; skipping stealth mode")

    async def save_session(self) -> None:
        """Save current browser session state to disk."""
        if self._context:
            state = await self._context.storage_state()
            self.session_store.save(state)

    async def close(self) -> None:
        """Close browser and clean up all resources."""
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Browser session closed")
        except Exception as e:
            logger.error("Error closing browser: %s", e)
            raise BrowserError(f"Browser cleanup failed: {e}", "BROWSER_CLOSE_ERROR")

    async def get_status(self) -> dict[str, Any]:
        """Return current browser/session status dict."""
        status: dict[str, Any] = {
            "browser_open": self._browser is not None,
            "context_ready": self._context is not None,
            "page_ready": self._page is not None,
            "current_url": None,
            "page_title": None,
            "in_studio": False,
            "session_saved": self.session_store.exists(),
        }
        if self._page:
            try:
                status["current_url"] = self._page.url
                status["page_title"] = await self._page.title()
                status["in_studio"] = "/studio" in (self._page.url or "")
            except Exception:
                pass
        return status
