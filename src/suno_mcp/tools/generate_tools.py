"""Music generation tools for Suno MCP."""

import asyncio
import logging
import sys
from typing import Optional

from ..browser.manager import BrowserManager
from ..browser.navigator import navigate_to, try_click, try_fill
from ..exceptions import SunoError

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)

CREATE_URL = "https://suno.com/create"


class GenerateTools:
    """Tools for generating music with Suno AI."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def generate_track(
        self,
        prompt: str,
        style: str = "synthwave",
        lyrics: Optional[str] = None,
        duration: str = "auto",
    ) -> str:
        """Generate a new music track using Suno AI."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            # Navigate to create page
            await navigate_to(page, CREATE_URL)
            await asyncio.sleep(2)

            # Fill song description / prompt
            prompt_selectors = [
                'textarea[placeholder*="Describe" i]',
                'textarea[placeholder*="song description" i]',
                'textarea[placeholder*="prompt" i]',
                'textarea[name="prompt"]',
                '[data-testid="prompt-input"]',
            ]
            filled = await try_fill(page, prompt_selectors, prompt)
            if not filled:
                raise SunoError("Prompt input field not found", "PROMPT_NOT_FOUND")

            # Fill lyrics if provided
            if lyrics:
                lyrics_selectors = [
                    'textarea[placeholder*="lyrics" i]',
                    'textarea[placeholder*="Lyrics" i]',
                    'textarea[name="lyrics"]',
                    '[data-testid="lyrics-input"]',
                ]
                await try_fill(page, lyrics_selectors, lyrics)

            # Click Create / Generate button
            generate_selectors = [
                'button:has-text("Create")',
                'button:has-text("Generate")',
                'button:has-text("Make Song")',
                'button[type="submit"]',
                '[data-testid="generate-button"]',
            ]
            clicked = await try_click(page, generate_selectors, timeout=5_000)
            if not clicked:
                raise SunoError("Generate button not found", "GENERATE_ERROR")

            await asyncio.sleep(3)

            return (
                f"🎵 Track generation initiated!\n"
                f"Prompt: \"{prompt}\"\n"
                f"Style: {style}\n"
                f"{f'Lyrics: {lyrics[:50]}...' if lyrics else ''}\n"
                f"Generation in progress. Use suno_library_list to check when complete."
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track generation failed: %s", e)
            raise SunoError(f"Track generation failed: {e}", "GENERATE_ERROR")
