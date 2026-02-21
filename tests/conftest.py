"""Shared fixtures for Suno MCP unit tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suno_mcp.browser.manager import BrowserManager
from suno_mcp.session.store import SessionStore


@pytest.fixture
def tmp_session_path(tmp_path: Path) -> Path:
    """Return a temporary path for session state storage."""
    return tmp_path / "session" / "storage_state.json"


@pytest.fixture
def session_store(tmp_session_path: Path) -> SessionStore:
    """SessionStore using a temporary path."""
    return SessionStore(path=tmp_session_path)


@pytest.fixture
def mock_page() -> AsyncMock:
    """Mock Playwright Page."""
    page = AsyncMock()
    page.url = "https://suno.com"
    page.title = AsyncMock(return_value="Suno AI")
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.locator = MagicMock()
    page.set_default_timeout = MagicMock()
    page.set_default_navigation_timeout = MagicMock()
    page.on = MagicMock()
    page.close = AsyncMock()
    # locator().first.click() chain
    mock_locator = AsyncMock()
    mock_locator.first = AsyncMock()
    mock_locator.first.click = AsyncMock()
    mock_locator.first.fill = AsyncMock()
    mock_locator.first.clear = AsyncMock()
    page.locator.return_value = mock_locator
    return page


@pytest.fixture
def mock_context(mock_page: AsyncMock) -> AsyncMock:
    """Mock Playwright BrowserContext."""
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=mock_page)
    context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
    context.close = AsyncMock()
    context.add_init_script = AsyncMock()
    return context


@pytest.fixture
def mock_browser(mock_context: AsyncMock) -> AsyncMock:
    """Mock Playwright Browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=mock_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser: AsyncMock) -> AsyncMock:
    """Mock Playwright instance."""
    pw = AsyncMock()
    pw.chromium = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    pw.stop = AsyncMock()
    return pw


@pytest.fixture
def browser_manager(session_store: SessionStore) -> BrowserManager:
    """BrowserManager with a temporary session store."""
    return BrowserManager(session_store=session_store)
