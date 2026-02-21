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
DEFAULT_WORKSPACE = "Just Game MCP"

# Fill a textarea by index (0=Lyrics, 1=Style, 2=Song Description in Custom mode).
# Triggers React's synthetic events so the UI state updates properly.
_JS_FILL_BY_INDEX = """
({index, text}) => {
    const textareas = [...document.querySelectorAll('textarea')].filter(t => t.offsetParent !== null);
    const el = textareas[index];
    if (!el) return null;
    el.focus();
    const desc = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
    if (desc && desc.set) desc.set.call(el, text);
    else el.value = text;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return el.placeholder || ('filled-index-' + index);
}
"""

# Fill by keyword match on placeholder/aria-label.
_JS_FILL_BY_KEYWORD = """
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
            if (desc && desc.set) desc.set.call(el, text);
            else el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return el.placeholder || 'keyword-matched';
        }
    }
    return null;
}
"""

# Click a button by text content. Does NOT skip disabled buttons — React may mark
# buttons disabled before content is entered, but we need to trigger the click anyway.
_JS_CLICK_BTN = """
(keywords) => {
    const buttons = [...document.querySelectorAll('button')];
    for (const btn of buttons) {
        const txt = (btn.textContent || btn.getAttribute('aria-label') || '').toLowerCase().trim();
        if (keywords.some(k => txt.includes(k)) && btn.offsetParent !== null) {
            btn.click();
            return txt;
        }
    }
    return null;
}
"""

_JS_DEBUG = """
() => {
    const textareas = [...document.querySelectorAll('textarea')].map((t, i) => ({
        index: i, ph: t.placeholder, name: t.name, visible: t.offsetParent !== null, chars: t.value.length
    }));
    const inputs = [...document.querySelectorAll('input')].map(i => ({
        ph: i.placeholder, type: i.type, name: i.name, visible: i.offsetParent !== null
    })).slice(0, 10);
    const buttons = [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent)
        .map(b => ({txt: b.textContent.trim(), disabled: b.disabled}))
        .filter(b => b.txt.length < 40)
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

            # Select workspace "Just Game MCP" before generating
            ws_result = await page.evaluate("""
(wsName) => {
    const wsBtn = [...document.querySelectorAll('button')]
        .find(b => b.innerText.trim() === 'Workspaces' && b.offsetParent);
    if (!wsBtn) return 'no_workspaces_btn';
    wsBtn.click();
    return 'opened';
}
""", DEFAULT_WORKSPACE)
            if ws_result == "opened":
                await asyncio.sleep(1)
                ws_selected = await page.evaluate("""
(wsName) => {
    const allText = [...document.querySelectorAll('li, [role="option"], [role="menuitem"], button')]
        .filter(el => el.offsetParent !== null);
    for (const el of allText) {
        if (el.innerText.trim() === wsName) { el.click(); return 'selected:' + wsName; }
    }
    return 'not_found';
}
""", DEFAULT_WORKSPACE)
                logger.info("Workspace selection: %s", ws_selected)
                await asyncio.sleep(0.5)

            # Enable Custom mode (unlocks Lyrics + Style of Music fields)
            custom_clicked = await page.evaluate(
                _JS_CLICK_BTN,
                ["custom", "커스텀", "custom mode"],
            )
            if custom_clicked:
                logger.info("Custom mode activated: %s", custom_clicked)
                await asyncio.sleep(1.5)
            else:
                logger.warning("Custom mode button not found — proceeding in simple mode")

            # In Custom mode, visible textareas are ordered: [0]=Lyrics, [1]=Style, [2]=Song Desc.
            # Use index-based fill for reliability (React placeholder text changes locale/version).
            if lyrics:
                lyric_result = await page.evaluate(
                    _JS_FILL_BY_INDEX,
                    {"index": 0, "text": lyrics},
                )
                logger.info("Lyrics fill result (index 0): %s", lyric_result)
                if not lyric_result:
                    # Fallback: keyword-based
                    lyric_result = await page.evaluate(
                        _JS_FILL_BY_KEYWORD,
                        {"keywords": ["lyric", "가사", "enter your lyrics", "write lyrics", "leave blank"], "text": lyrics},
                    )
                    logger.info("Lyrics fill fallback: %s", lyric_result)

            if style and custom_clicked:
                style_result = await page.evaluate(
                    _JS_FILL_BY_INDEX,
                    {"index": 1, "text": style},
                )
                logger.info("Style fill result (index 1): %s", style_result)
                if not style_result:
                    # Fallback: keyword-based — placeholder is style examples, so try unique substrings
                    style_result = await page.evaluate(
                        _JS_FILL_BY_KEYWORD,
                        {"keywords": ["nepali", "italiano", "folk", "style of music"], "text": style},
                    )
                    logger.info("Style fill fallback: %s", style_result)

            # Song Description: index 2 in custom mode, index 0 in simple mode
            desc_index = 2 if custom_clicked else 0
            prompt_result = await page.evaluate(
                _JS_FILL_BY_INDEX,
                {"index": desc_index, "text": prompt},
            )
            logger.info("Prompt fill result (index %d): %s", desc_index, prompt_result)
            if not prompt_result:
                # Fallback: keyword-based
                prompt_result = await page.evaluate(
                    _JS_FILL_BY_KEYWORD,
                    {"keywords": ["describe", "song description", "song desc", "prompt", "describe your", "aggressive"], "text": prompt},
                )
                logger.info("Prompt fill fallback: %s", prompt_result)
            if not prompt_result:
                debug2 = await page.evaluate(_JS_DEBUG)
                raise SunoError(
                    f"Prompt input field not found. Page state: {debug2}",
                    "PROMPT_NOT_FOUND",
                )

            # Small pause to let React enable the Create button
            await asyncio.sleep(0.5)

            # Click Create / Generate button (does NOT filter by disabled — React may still
            # show it as disabled but accept the click once fields are filled)
            generate_clicked = await page.evaluate(
                _JS_CLICK_BTN,
                ["create", "generate", "make song", "만들기", "생성"],
            )
            if not generate_clicked:
                debug3 = await page.evaluate(_JS_DEBUG)
                raise SunoError(f"Generate button not found. Buttons: {debug3.get('buttons')}", "GENERATE_ERROR")

            await asyncio.sleep(3)

            return (
                f"Track generation initiated!\n"
                f"Workspace: {DEFAULT_WORKSPACE}\n"
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
