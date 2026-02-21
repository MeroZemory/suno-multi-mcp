"""Unit tests for BrowserManager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suno_mcp.browser.manager import BrowserManager
from suno_mcp.exceptions import BrowserError
from suno_mcp.session.store import SessionStore


async def test_ensure_browser_initializes_all_components(
    browser_manager: BrowserManager,
    mock_playwright: AsyncMock,
    mock_browser: AsyncMock,
    mock_context: AsyncMock,
    mock_page: AsyncMock,
) -> None:
    with patch("suno_mcp.browser.manager.async_playwright") as mock_ap:
        mock_ap.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        components = await browser_manager.ensure_browser(headless=True)

    assert components["playwright"] is not None
    assert components["browser"] is not None


async def test_get_status_when_no_browser(session_store: SessionStore) -> None:
    manager = BrowserManager(session_store=session_store)
    status = await manager.get_status()
    assert status["browser_open"] is False
    assert status["page_ready"] is False
    assert status["context_ready"] is False
    assert status["current_url"] is None


async def test_get_status_with_page(
    browser_manager: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    browser_manager._page = mock_page
    browser_manager._browser = AsyncMock()
    browser_manager._context = AsyncMock()
    mock_page.url = "https://suno.com/create"
    mock_page.title = AsyncMock(return_value="Suno Create")

    status = await browser_manager.get_status()
    assert status["browser_open"] is True
    assert status["page_ready"] is True
    assert status["current_url"] == "https://suno.com/create"
    assert status["in_studio"] is False


async def test_save_session_calls_storage_state(
    browser_manager: BrowserManager,
    session_store: SessionStore,
    mock_context: AsyncMock,
) -> None:
    browser_manager._context = mock_context
    mock_context.storage_state = AsyncMock(return_value={"cookies": [{"name": "t", "value": "v"}]})

    await browser_manager.save_session()
    assert session_store.exists()
    loaded = session_store.load()
    assert loaded is not None
    assert loaded["cookies"][0]["name"] == "t"


async def test_close_resets_all_state(
    browser_manager: BrowserManager,
    mock_page: AsyncMock,
    mock_context: AsyncMock,
    mock_browser: AsyncMock,
    mock_playwright: AsyncMock,
) -> None:
    browser_manager._page = mock_page
    browser_manager._context = mock_context
    browser_manager._browser = mock_browser
    browser_manager._playwright = mock_playwright

    await browser_manager.close()

    assert browser_manager._page is None
    assert browser_manager._context is None
    assert browser_manager._browser is None
    assert browser_manager._playwright is None
