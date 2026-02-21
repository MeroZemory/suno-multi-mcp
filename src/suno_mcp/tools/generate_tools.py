"""Music generation tools for Suno MCP."""

import asyncio
import logging
import sys
from typing import Optional

from ..browser.manager import BrowserManager
from ..browser.navigator import navigate_to
from ..exceptions import SunoError

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)

CREATE_URL = "https://suno.com/create"

# Playwright evaluate() only accepts (js, single_arg).
# Pass {"keywords": [...], "text": "..."} as the single arg.
_JS_FILL = """
({keywords, text}) => {
    const all = [...document.querySelectorAll('textarea, input[type="text"]')];
    for (const el of all) {
        const ph = (el.placeholder || el.getAttribute('aria-label') || '').toLowerCase();
        if (keywords.some(k => ph.includes(k)) && el.offsetParent !== null) {
            el.focus();
            const desc = Object.getOwnPropertyDescriptor(
                el.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype,
                'value'
            );
            if (desc && desc.set) {
                desc.set.call(el, text);
            } else {
                el.value = text;
            }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return el.placeholder || 'matched';
        }
    }
    // Fallback: first visible textarea
    for (const el of all) {
        if (el.tagName === 'TEXTAREA' && el.offsetParent !== null) {
            el.focus();
            el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return 'fallback:' + (el.placeholder || 'textarea');
        }
    }
    // Contenteditable
    const ces = [...document.querySelectorAll('[contenteditable="true"]')];
    for (const el of ces) {
        if (el.offsetParent !== null) {
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
            return 'contenteditable';
        }
    }
    return null;
}
"""

_JS_CLICK_BTN = """
(keywords) => {
    const buttons = [...document.querySelectorAll('button')];
    for (const btn of buttons) {
        const txt = (btn.textContent || btn.getAttribute('aria-label') || '').toLowerCase().trim();
        if (keywords.some(k => txt.includes(k)) && btn.offsetParent !== null && !btn.disabled) {
            btn.click();
            return txt;
        }
    }
    return null;
}
"""

_JS_DEBUG = """
() => {
    const textareas = [...document.querySelectorAll('textarea')].map(t => ({
        ph: t.placeholder, name: t.name, visible: t.offsetParent !== null
    }));
    const inputs = [...document.querySelectorAll('input')].map(i => ({
        ph: i.placeholder, type: i.type, name: i.name, visible: i.offsetParent !== null
    })).slice(0, 10);
    const buttons = [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent)
        .map(b => b.textContent.trim())
        .filter(t => t.length < 40)
        .slice(0, 20);
    return {textareas, inputs, buttons, url: location.href};
}
"""


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

            # Navigate to create page; React SPA needs extra settle time
            await navigate_to(page, CREATE_URL)
            await asyncio.sleep(4)

            # Debug: log page state
            debug = await page.evaluate(_JS_DEBUG)
            logger.info("Create page state: %s", debug)

            # Enable Custom mode (unlocks Lyrics + Style of Music fields)
            custom_clicked = await page.evaluate(
                _JS_CLICK_BTN,
                ["custom", "커스텀", "custom mode"],
            )
            if custom_clicked:
                logger.info("Custom mode activated: %s", custom_clicked)
                await asyncio.sleep(1.5)

            # Fill Lyrics field (Custom mode)
            if lyrics:
                lyric_result = await page.evaluate(
                    _JS_FILL,
                    {"keywords": ["lyric", "가사", "enter your lyrics", "write lyrics"], "text": lyrics},
                )
                logger.info("Lyrics fill result: %s", lyric_result)

            # Fill Style of Music field
            if style:
                style_result = await page.evaluate(
                    _JS_FILL,
                    {"keywords": ["style", "genre", "music style", "style of music"], "text": style},
                )
                logger.info("Style fill result: %s", style_result)

            # Fill main prompt / Song Description
            prompt_result = await page.evaluate(
                _JS_FILL,
                {"keywords": ["describe", "song description", "song desc", "prompt", "describe your"], "text": prompt},
            )
            if not prompt_result:
                # Fallback: fill first visible textarea
                prompt_result = await page.evaluate(
                    _JS_FILL,
                    {"keywords": [], "text": prompt},
                )
            if not prompt_result:
                debug2 = await page.evaluate(_JS_DEBUG)
                raise SunoError(
                    f"Prompt input field not found. Page state: {debug2}",
                    "PROMPT_NOT_FOUND",
                )
            logger.info("Prompt fill result: %s", prompt_result)

            # Click Create / Generate button
            generate_clicked = await page.evaluate(
                _JS_CLICK_BTN,
                ["create", "generate", "make song", "만들기", "생성"],
            )
            if not generate_clicked:
                raise SunoError("Generate button not found", "GENERATE_ERROR")

            await asyncio.sleep(3)

            return (
                f"🎵 Track generation initiated!\n"
                f"Prompt: \"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\"\n"
                f"Style: {style}\n"
                f"{'Lyrics: ' + str(len(lyrics)) + ' chars' if lyrics else 'No custom lyrics'}\n"
                f"Custom mode: {'activated' if custom_clicked else 'not found (simple mode)'}\n"
                f"Use suno_library_list to check when complete."
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track generation failed: %s", e)
            raise SunoError(f"Track generation failed: {e}", "GENERATE_ERROR")
