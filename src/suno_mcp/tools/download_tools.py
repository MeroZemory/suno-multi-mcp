"""Download tools for Suno MCP."""

import asyncio
import logging
import sys
from pathlib import Path

from ..browser.manager import BrowserManager
from ..browser.navigator import navigate_to, try_click
from ..exceptions import SunoError

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)


class DownloadTools:
    """Tools for downloading tracks from Suno AI."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def download_track(
        self,
        track_id: str,
        download_path: str = "downloads/",
        include_stems: bool = False,
    ) -> str:
        """Download a track from Suno AI by track ID."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            download_dir = Path(download_path)
            download_dir.mkdir(parents=True, exist_ok=True)

            # Navigate to the track page
            track_url = f"https://suno.com/song/{track_id}"
            await navigate_to(page, track_url)
            await asyncio.sleep(2)

            # Start download event listener
            download_event = page.wait_for_event("download", timeout=15_000)

            # Click download / more options button
            download_selectors = [
                'button:has-text("Download")',
                'button[aria-label*="download" i]',
                '[data-testid="download-button"]',
                'a:has-text("Download")',
                'button:has-text("...")',
                'button[aria-label="More options"]',
            ]
            clicked = await try_click(page, download_selectors, timeout=5_000)
            if not clicked:
                raise SunoError("Download button not found", "DOWNLOAD_ERROR")

            # If we clicked "...", look for Download in the context menu
            try:
                await try_click(
                    page,
                    ['[role="menuitem"]:has-text("Download")', 'li:has-text("Download")'],
                    timeout=3_000,
                )
            except Exception:
                pass

            # Wait for download to start
            try:
                download = await download_event
                filename = download.suggested_filename
                filepath = download_dir / filename
                await download.save_as(str(filepath))
                return (
                    f"✅ Download completed!\n"
                    f"Track: {filename}\n"
                    f"Path: {filepath}\n"
                    f"Track ID: {track_id}"
                )
            except Exception as e:
                raise SunoError(f"Download did not complete: {e}", "DOWNLOAD_TIMEOUT")

        except SunoError:
            raise
        except Exception as e:
            logger.error("Download failed: %s", e)
            raise SunoError(f"Download failed: {e}", "DOWNLOAD_ERROR")
