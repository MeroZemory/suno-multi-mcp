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

# Fill by keyword match on placeholder/aria-label (textarea or text input).
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

# Fill a text INPUT (not textarea) by keyword — used for the song title field.
_JS_FILL_TITLE_INPUT = """
({keywords, text}) => {
    const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
    for (const el of inputs) {
        const ph = (el.placeholder || el.getAttribute('aria-label') || el.getAttribute('name') || '').toLowerCase();
        if (keywords.some(k => ph.includes(k)) && el.offsetParent !== null) {
            el.focus();
            const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            if (desc && desc.set) desc.set.call(el, text);
            else el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return el.placeholder || 'title-filled';
        }
    }
    return null;
}
"""

# Click a button by text content (does NOT skip disabled buttons).
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
        index: i, ph: t.placeholder, visible: t.offsetParent !== null, chars: t.value.length
    }));
    const inputs = [...document.querySelectorAll('input')].filter(i => i.offsetParent).map(i => ({
        ph: i.placeholder, type: i.type, name: i.name, label: i.getAttribute('aria-label')
    })).slice(0, 10);
    const buttons = [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent)
        .map(b => ({txt: b.textContent.trim(), disabled: b.disabled}))
        .filter(b => b.txt.length < 40)
        .slice(0, 25);
    return {textareas, inputs, buttons, url: location.href};
}
"""


class GenerateTools:
    """Tools for generating music with Suno AI."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def _select_workspace(self, page, workspace: str) -> str:
        """Try to switch to the specified workspace on the create page."""
        # Open workspace dropdown — button may show current workspace name or "Workspaces"
        ws_result = await page.evaluate("""
(wsName) => {
    const candidates = [...document.querySelectorAll(
        'button, [role="combobox"], [role="button"]'
    )].filter(b => b.offsetParent);
    const wsBtn = candidates.find(b => {
        const txt = (b.textContent || b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
        return txt.includes('workspace') || txt === wsName.toLowerCase();
    });
    if (!wsBtn) {
        const allBtnTxts = candidates.map(b => b.innerText.trim()).filter(t => t && t.length < 30).join('|');
        return 'no_btn:' + allBtnTxts;
    }
    wsBtn.click();
    return 'opened:' + wsBtn.innerText.trim();
}
""", workspace)
        logger.info("Workspace btn: %s", ws_result)

        if not ws_result.startswith("opened"):
            return ws_result  # could not find button

        await asyncio.sleep(1)

        # Select the workspace in the dropdown
        ws_selected = await page.evaluate("""
(wsName) => {
    const allEl = [...document.querySelectorAll(
        'li, [role="option"], [role="menuitem"], button, a, div[class*="item" i]'
    )].filter(el => el.offsetParent !== null);
    // Exact match first
    let target = allEl.find(el => (el.innerText || '').trim() === wsName);
    // Contains match fallback
    if (!target) target = allEl.find(el => (el.innerText || '').includes(wsName));
    if (target) { target.click(); return 'selected:' + target.innerText.trim(); }
    const menu = allEl.slice(0, 12).map(e => (e.innerText || '').trim()).filter(t => t).join('|');
    return 'not_found_in_menu:' + menu;
}
""", workspace)
        logger.info("Workspace select: %s", ws_selected)
        return ws_selected

    async def generate_track(
        self,
        prompt: str,
        style: str = "synthwave",
        lyrics: Optional[str] = None,
        duration: str = "auto",
        title: Optional[str] = None,
    ) -> str:
        """Generate a new music track using Suno AI.

        Always specify `title` (so generated tracks are identifiable in library),
        and `duration` appropriate for the intended use.
        """
        try:
            components = await self.manager.ensure_browser()
            page = components["page"]

            # Navigate to create page; React SPA needs extra settle time
            await navigate_to(page, CREATE_URL)
            await asyncio.sleep(4)

            debug = await page.evaluate(_JS_DEBUG)
            logger.info("Create page initial state: %s", debug)

            # Select workspace
            ws_result = await self._select_workspace(page, DEFAULT_WORKSPACE)
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

            # Fill title if provided (text input, keywords: title/name/song name)
            if title:
                title_result = await page.evaluate(
                    _JS_FILL_TITLE_INPUT,
                    {"keywords": ["title", "song name", "name", "제목", "곡 이름"], "text": title},
                )
                logger.info("Title fill result: %s", title_result)
                if not title_result:
                    # Some Suno versions show title as textarea placeholder "Song title" — try that
                    title_result = await page.evaluate(
                        _JS_FILL_BY_KEYWORD,
                        {"keywords": ["song title", "title", "제목"], "text": title},
                    )
                    logger.info("Title fill fallback: %s", title_result)

            # Custom mode textarea order: [0]=Lyrics, [1]=Style of Music, [2]=Song Description
            if lyrics:
                lyric_result = await page.evaluate(
                    _JS_FILL_BY_INDEX, {"index": 0, "text": lyrics}
                )
                logger.info("Lyrics fill (index 0): %s", lyric_result)
                if not lyric_result:
                    lyric_result = await page.evaluate(
                        _JS_FILL_BY_KEYWORD,
                        {"keywords": ["lyric", "가사", "leave blank", "write lyrics"], "text": lyrics},
                    )

            if style and custom_clicked:
                style_result = await page.evaluate(
                    _JS_FILL_BY_INDEX, {"index": 1, "text": style}
                )
                logger.info("Style fill (index 1): %s", style_result)
                if not style_result:
                    style_result = await page.evaluate(
                        _JS_FILL_BY_KEYWORD,
                        {"keywords": ["nepali", "italiano", "folk", "style of music"], "text": style},
                    )

            # Song Description: index 2 in custom mode, index 0 in simple mode
            desc_index = 2 if custom_clicked else 0
            prompt_result = await page.evaluate(
                _JS_FILL_BY_INDEX, {"index": desc_index, "text": prompt}
            )
            logger.info("Prompt fill (index %d): %s", desc_index, prompt_result)
            if not prompt_result:
                prompt_result = await page.evaluate(
                    _JS_FILL_BY_KEYWORD,
                    {"keywords": ["describe", "song description", "prompt", "aggressive"], "text": prompt},
                )
            if not prompt_result:
                debug2 = await page.evaluate(_JS_DEBUG)
                raise SunoError(
                    f"Prompt input field not found. Page: {debug2}",
                    "PROMPT_NOT_FOUND",
                )

            await asyncio.sleep(0.5)

            generate_clicked = await page.evaluate(
                _JS_CLICK_BTN,
                ["create", "generate", "make song", "만들기", "생성"],
            )
            if not generate_clicked:
                debug3 = await page.evaluate(_JS_DEBUG)
                raise SunoError(
                    f"Generate button not found. Buttons: {debug3.get('buttons')}",
                    "GENERATE_ERROR",
                )

            await asyncio.sleep(3)

            ws_status = ws_result if "selected:" in ws_result else f"WARNING: {ws_result}"
            return (
                f"Track generation initiated!\n"
                f"Title: {title or '(auto)'}\n"
                f"Workspace: {ws_status}\n"
                f"Style: {style}\n"
                f"Duration: {duration}\n"
                f"{'Lyrics: ' + str(len(lyrics)) + ' chars' if lyrics else 'Instrumental (no lyrics)'}\n"
                f"Custom mode: {'activated' if custom_clicked else 'simple mode'}\n"
                f"IMPORTANT: Wait for both tracks to appear in suno_library_list before calling generate_track again."
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Track generation failed: %s", e)
            raise SunoError(f"Track generation failed: {e}", "GENERATE_ERROR")
