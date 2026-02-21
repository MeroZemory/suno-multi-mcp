"""Library and studio tools for Suno MCP — real suno.com UI automation."""

import asyncio
import json
import logging
import re
import sys
from typing import Optional

from ..browser.manager import BrowserManager
from ..browser.navigator import find_visible, navigate_to, try_click, try_fill
from ..exceptions import SunoError

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)


class LibraryTools:
    """Tools for browsing and interacting with the Suno AI library."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def library_list(self, limit: int = 20) -> str:
        """List tracks from the Suno AI library."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            await navigate_to(page, "https://suno.com/me")
            await asyncio.sleep(2)

            # Wait for track cards to appear
            card_selectors = [
                '[data-testid="song-card"]',
                '.song-card',
                'a[href*="/song/"]',
                '[class*="SongCard"]',
                '[class*="song-card"]',
                '[class*="track-card"]',
            ]
            found_sel = await find_visible(page, card_selectors, timeout=8_000)
            if not found_sel:
                return "📭 No tracks found in library, or not logged in."

            # Extract track information from the page
            tracks = await page.evaluate("""() => {
                const results = [];
                // Try common selectors for song cards
                const cards = document.querySelectorAll(
                    '[data-testid="song-card"], .song-card, [class*="SongCard"], [class*="song-card"]'
                );
                cards.forEach((card, index) => {
                    if (index >= 50) return; // cap at 50
                    const link = card.querySelector('a[href*="/song/"]') || card.closest('a[href*="/song/"]');
                    const href = link ? link.href : '';
                    const idMatch = href.match(/\\/song\\/([a-zA-Z0-9_-]+)/);
                    const trackId = idMatch ? idMatch[1] : null;

                    const titleEl = card.querySelector('[class*="title"], [class*="Title"], h3, h2, h4');
                    const title = titleEl ? titleEl.textContent.trim() : 'Unknown';

                    const durationEl = card.querySelector('[class*="duration"], [class*="Duration"], time');
                    const duration = durationEl ? durationEl.textContent.trim() : '';

                    if (trackId) {
                        results.push({ id: trackId, title, duration, url: href });
                    }
                });
                return results;
            }""")

            if not tracks:
                # Fallback: extract track IDs from all /song/ links on the page
                tracks = await page.evaluate("""() => {
                    const seen = new Set();
                    const results = [];
                    document.querySelectorAll('a[href*="/song/"]').forEach(a => {
                        const m = a.href.match(/\\/song\\/([a-zA-Z0-9_-]+)/);
                        if (m && !seen.has(m[1])) {
                            seen.add(m[1]);
                            results.push({ id: m[1], title: a.textContent.trim() || 'Track', url: a.href });
                        }
                    });
                    return results;
                }""")

            tracks = tracks[:limit]
            track_list = json.dumps(tracks, ensure_ascii=False, indent=2)
            return f"🎵 Library ({len(tracks)} tracks):\n```json\n{track_list}\n```"

        except SunoError:
            raise
        except Exception as e:
            logger.error("Library list failed: %s", e)
            raise SunoError(f"Library list failed: {e}", "LIBRARY_ERROR")

    async def track_info(self, track_id: str) -> str:
        """Get detailed information about a specific track."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            await navigate_to(page, f"https://suno.com/song/{track_id}")
            await asyncio.sleep(2)

            info = await page.evaluate("""() => {
                const get = (selectors) => {
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) return el.textContent.trim();
                    }
                    return null;
                };
                const title = get(['h1', '[class*="title" i]', '[class*="Title"]']);
                const style = get(['[class*="style" i]', '[class*="tag"]', '[data-testid="style"]']);
                const duration = get(['[class*="duration" i]', 'time', '[class*="Duration"]']);

                // Try to extract lyrics
                const lyricsEl = document.querySelector('[class*="lyric" i], [class*="Lyric"], [data-testid="lyrics"]');
                const lyrics = lyricsEl ? lyricsEl.textContent.trim().slice(0, 500) : null;

                return { title, style, duration, lyrics };
            }""")

            result = {
                "track_id": track_id,
                "url": f"https://suno.com/song/{track_id}",
                **info,
            }
            return f"🎵 Track Info:\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```"

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track info failed: %s", e)
            raise SunoError(f"Track info failed: {e}", "TRACK_INFO_ERROR")

    async def track_extend(self, track_id: str, prompt: str, duration: int = 15) -> str:
        """Extend an existing track with additional content."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            await navigate_to(page, f"https://suno.com/song/{track_id}")
            await asyncio.sleep(2)

            # Click "..." (more options) or direct Extend button
            extend_btn = await find_visible(
                page,
                [
                    'button:has-text("Extend")',
                    '[data-testid="extend-button"]',
                    'button[aria-label*="extend" i]',
                ],
                timeout=3_000,
            )

            if extend_btn:
                await try_click(page, [extend_btn], timeout=3_000)
            else:
                # Try "..." menu first
                clicked = await try_click(
                    page,
                    [
                        'button[aria-label="More options"]',
                        'button:has-text("...")',
                        '[data-testid="more-button"]',
                    ],
                    timeout=3_000,
                )
                if clicked:
                    await asyncio.sleep(0.5)
                    await try_click(
                        page,
                        [
                            '[role="menuitem"]:has-text("Extend")',
                            'li:has-text("Extend")',
                            'button:has-text("Extend")',
                        ],
                        timeout=3_000,
                    )
                else:
                    raise SunoError("Extend button not found", "EXTEND_NOT_FOUND")

            await asyncio.sleep(1)

            # Fill the extend prompt
            prompt_selectors = [
                'textarea[placeholder*="extend" i]',
                'textarea[placeholder*="Continue" i]',
                'textarea[placeholder*="prompt" i]',
                'textarea',
            ]
            filled = await try_fill(page, prompt_selectors, prompt)
            if not filled:
                raise SunoError("Extend prompt field not found", "EXTEND_PROMPT_NOT_FOUND")

            # Submit
            submit_selectors = [
                'button:has-text("Extend")',
                'button:has-text("Create")',
                'button[type="submit"]',
                'button:has-text("Generate")',
            ]
            clicked = await try_click(page, submit_selectors, timeout=5_000)
            if not clicked:
                raise SunoError("Extend submit button not found", "EXTEND_SUBMIT_NOT_FOUND")

            await asyncio.sleep(2)
            return (
                f"✅ Track extension initiated!\n"
                f"Track ID: {track_id}\n"
                f"Prompt: \"{prompt}\"\n"
                f"Duration: {duration}s\n"
                f"Check suno_library_list for the new extended track."
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track extend failed: %s", e)
            raise SunoError(f"Track extend failed: {e}", "EXTEND_ERROR")

    async def track_remix(self, track_id: str, prompt: str, style: str = "") -> str:
        """Remix/cover an existing track with a new prompt."""
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            await navigate_to(page, f"https://suno.com/song/{track_id}")
            await asyncio.sleep(2)

            # Click Remix/Cover button or find it in "..." menu
            remix_btn = await find_visible(
                page,
                [
                    'button:has-text("Remix")',
                    'button:has-text("Cover")',
                    '[data-testid="remix-button"]',
                    'button[aria-label*="remix" i]',
                ],
                timeout=3_000,
            )

            if remix_btn:
                await try_click(page, [remix_btn], timeout=3_000)
            else:
                clicked = await try_click(
                    page,
                    [
                        'button[aria-label="More options"]',
                        'button:has-text("...")',
                        '[data-testid="more-button"]',
                    ],
                    timeout=3_000,
                )
                if clicked:
                    await asyncio.sleep(0.5)
                    await try_click(
                        page,
                        [
                            '[role="menuitem"]:has-text("Remix")',
                            '[role="menuitem"]:has-text("Cover")',
                            'li:has-text("Remix")',
                        ],
                        timeout=3_000,
                    )
                else:
                    raise SunoError("Remix button not found", "REMIX_NOT_FOUND")

            await asyncio.sleep(1)

            # Fill remix prompt
            prompt_selectors = [
                'textarea[placeholder*="Describe" i]',
                'textarea[placeholder*="prompt" i]',
                'textarea[placeholder*="style" i]',
                'textarea',
            ]
            filled = await try_fill(page, prompt_selectors, prompt)
            if not filled:
                raise SunoError("Remix prompt field not found", "REMIX_PROMPT_NOT_FOUND")

            # Fill style if provided
            if style:
                style_selectors = [
                    'input[placeholder*="style" i]',
                    'textarea[placeholder*="style" i]',
                    '[data-testid="style-input"]',
                ]
                await try_fill(page, style_selectors, style)

            # Submit
            submit_selectors = [
                'button:has-text("Remix")',
                'button:has-text("Create")',
                'button[type="submit"]',
                'button:has-text("Generate")',
            ]
            clicked = await try_click(page, submit_selectors, timeout=5_000)
            if not clicked:
                raise SunoError("Remix submit button not found", "REMIX_SUBMIT_NOT_FOUND")

            await asyncio.sleep(2)
            return (
                f"✅ Track remix initiated!\n"
                f"Original Track ID: {track_id}\n"
                f"Prompt: \"{prompt}\"\n"
                f"{f'Style: {style}' if style else ''}\n"
                f"Check suno_library_list for the new remix."
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track remix failed: %s", e)
            raise SunoError(f"Track remix failed: {e}", "REMIX_ERROR")
