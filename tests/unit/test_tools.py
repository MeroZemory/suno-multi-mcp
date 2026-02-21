"""Unit tests for Suno MCP tool classes."""

import importlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suno_mcp.browser.manager import BrowserManager
from suno_mcp.exceptions import AuthError, BrowserError, SunoError
from suno_mcp.session.store import SessionStore
from suno_mcp.tools.browser_tools import BrowserTools
from suno_mcp.tools.generate_tools import GenerateTools

# LibraryTools is written by a separate agent (Phase 3).
# Import it conditionally so tests for other tools are not blocked.
try:
    from suno_mcp.tools.library_tools import LibraryTools

    _LIBRARY_TOOLS_AVAILABLE = True
except ImportError:
    LibraryTools = None  # type: ignore[assignment,misc]
    _LIBRARY_TOOLS_AVAILABLE = False

library_tools_required = pytest.mark.skipif(
    not _LIBRARY_TOOLS_AVAILABLE,
    reason="suno_mcp.tools.library_tools not yet implemented (Phase 3 pending)",
)


@pytest.fixture
def manager_with_page(
    browser_manager: BrowserManager,
    mock_page: AsyncMock,
    mock_context: AsyncMock,
    mock_browser: AsyncMock,
    mock_playwright: AsyncMock,
) -> BrowserManager:
    """BrowserManager pre-loaded with mock browser components."""
    browser_manager._page = mock_page
    browser_manager._context = mock_context
    browser_manager._browser = mock_browser
    browser_manager._playwright = mock_playwright
    return browser_manager


# ── BrowserTools ──────────────────────────────────────────────────────────────

async def test_open_browser_returns_success(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    mock_page.title = AsyncMock(return_value="Suno AI")
    mock_page.url = "https://suno.com"
    mock_page.goto = AsyncMock()

    tools = BrowserTools(manager_with_page)
    with patch.object(manager_with_page, "ensure_browser", return_value={
        "page": mock_page, "browser": AsyncMock(), "context": AsyncMock(), "playwright": AsyncMock()
    }):
        result = await tools.open_browser()
    assert "✅" in result
    assert "Browser opened" in result


async def test_get_status_returns_formatted_string(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    mock_page.url = "https://suno.com/create"
    mock_page.title = AsyncMock(return_value="Suno")

    tools = BrowserTools(manager_with_page)
    result = await tools.get_status()
    assert "Suno MCP Status" in result
    assert "Browser Open" in result


async def test_close_browser_returns_success(manager_with_page: BrowserManager) -> None:
    tools = BrowserTools(manager_with_page)
    with patch.object(manager_with_page, "close", return_value=None) as mock_close:
        result = await tools.close_browser()
    assert "✅" in result
    mock_close.assert_called_once()


# ── GenerateTools ─────────────────────────────────────────────────────────────

async def test_generate_track_success(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    mock_page.url = "https://suno.com/create"
    mock_locator = AsyncMock()
    mock_locator.first = AsyncMock()
    mock_locator.first.clear = AsyncMock()
    mock_locator.first.fill = AsyncMock()
    mock_locator.first.click = AsyncMock()
    mock_page.locator.return_value = mock_locator
    mock_page.wait_for_selector = AsyncMock()

    tools = GenerateTools(manager_with_page)
    with patch.object(manager_with_page, "ensure_browser", return_value={
        "page": mock_page, "browser": AsyncMock(), "context": AsyncMock(), "playwright": AsyncMock()
    }):
        result = await tools.generate_track("dark epic orchestral")
    assert "🎵" in result
    assert "dark epic orchestral" in result


# ── LibraryTools ──────────────────────────────────────────────────────────────

@library_tools_required
async def test_library_list_returns_tracks(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    mock_page.evaluate = AsyncMock(return_value=[
        {"id": "abc123", "title": "Test Song", "duration": "2:30", "url": "https://suno.com/song/abc123"}
    ])
    mock_page.wait_for_selector = AsyncMock()

    tools = LibraryTools(manager_with_page)
    with patch.object(manager_with_page, "ensure_browser", return_value={
        "page": mock_page, "browser": AsyncMock(), "context": AsyncMock(), "playwright": AsyncMock()
    }):
        with patch("suno_mcp.tools.library_tools.find_visible", return_value='a[href*="/song/"]'):
            result = await tools.library_list(limit=10)
    assert "abc123" in result


@library_tools_required
async def test_track_info_returns_details(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    mock_page.evaluate = AsyncMock(return_value={
        "title": "Epic Battle Theme",
        "style": "dark orchestral",
        "duration": "3:45",
        "lyrics": None,
    })

    tools = LibraryTools(manager_with_page)
    with patch.object(manager_with_page, "ensure_browser", return_value={
        "page": mock_page, "browser": AsyncMock(), "context": AsyncMock(), "playwright": AsyncMock()
    }):
        result = await tools.track_info("abc123")
    assert "abc123" in result
    assert "Epic Battle Theme" in result


@library_tools_required
async def test_library_list_no_tracks(
    manager_with_page: BrowserManager,
    mock_page: AsyncMock,
) -> None:
    tools = LibraryTools(manager_with_page)
    with patch.object(manager_with_page, "ensure_browser", return_value={
        "page": mock_page, "browser": AsyncMock(), "context": AsyncMock(), "playwright": AsyncMock()
    }):
        with patch("suno_mcp.tools.library_tools.find_visible", return_value=None):
            result = await tools.library_list()
    assert "No tracks" in result or "not logged in" in result
