#!/usr/bin/env python3
"""Suno MCP Server — FastMCP stdio implementation."""

import asyncio
import logging
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .browser.manager import BrowserManager
from .session.store import SessionStore
from .tools.auth_tools import AuthTools
from .tools.browser_tools import BrowserTools
from .tools.download_tools import DownloadTools
from .tools.generate_tools import GenerateTools
from .tools.library_tools import LibraryTools

# Configure logging to stderr (stdout is reserved for JSON-RPC)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# Shared manager instance
_session_store = SessionStore()
_manager = BrowserManager(session_store=_session_store)

# Tool instances
_browser = BrowserTools(_manager)
_auth = AuthTools(_manager)
_generate = GenerateTools(_manager)
_download = DownloadTools(_manager)
_library = LibraryTools(_manager)

# FastMCP app
mcp = FastMCP("suno-mcp")


# ── Browser tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def suno_open_browser(headless: bool = False) -> str:
    """Open Chrome browser with stealth mode for Suno AI.

    Args:
        headless: Run in headless mode. Default False (headful) for Google OAuth.
    """
    return await _browser.open_browser(headless=headless)


@mcp.tool()
async def suno_get_status() -> str:
    """Get current Suno AI session status (browser, page, session persistence)."""
    return await _browser.get_status()


@mcp.tool()
async def suno_close_browser() -> str:
    """Close the Playwright browser session and clean up resources."""
    return await _browser.close_browser()


# ── Auth tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def suno_login(email: str, password: str) -> str:
    """Login to Suno AI via Google OAuth. Saves session for future use.

    Args:
        email: Google account email (e.g. your-account@gmail.com)
        password: Google account password
    """
    return await _auth.login(email, password)


# ── Generate tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def suno_generate_track(
    prompt: str,
    style: str = "synthwave",
    lyrics: Optional[str] = None,
    duration: str = "auto",
    title: Optional[str] = None,
) -> str:
    """Generate a new music track using Suno AI.

    RULES (always follow):
    1. Always specify `title` — makes the generated track identifiable in the library.
    2. Always specify `duration` appropriate to the use case:
       - "short" (~30s): stings, transitions, short loops
       - "medium" (~60-90s): preparation screens, menus, short loops
       - "long" (2-3min): battle themes, title screen, boss fights, cutscenes
       - "auto": only when duration doesn't matter
    3. NEVER call this tool again before confirming the previous two tracks
       appeared in suno_library_list — calling too fast triggers CAPTCHA.
    4. All tracks go to the "Just Game MCP" workspace automatically.

    Args:
        prompt: Song Description — what the music should convey, mood, context
        style: Style of Music field — genre tags (e.g. "dark ambient, taiko drums, cinematic")
        lyrics: Custom lyrics (leave None for instrumental)
        duration: Track length hint — "short" / "medium" / "long" / "auto"
        title: Desired track title (shown in library — always specify this)
    """
    return await _generate.generate_track(prompt, style, lyrics, duration, title)


# ── Download tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def suno_download_track(
    track_id: str,
    download_path: str = "downloads/",
    include_stems: bool = False,
) -> str:
    """Download a generated track from Suno AI by track ID.

    Args:
        track_id: The unique track identifier
        download_path: Directory to save the file
        include_stems: Download individual stems if available
    """
    return await _download.download_track(track_id, download_path, include_stems)


# ── Library / Studio tools ─────────────────────────────────────────────────────

@mcp.tool()
async def suno_library_list(limit: int = 20) -> str:
    """List tracks from your Suno AI library (requires login).

    Args:
        limit: Maximum number of tracks to return (default: 20)
    """
    return await _library.library_list(limit)


@mcp.tool()
async def suno_track_info(track_id: str) -> str:
    """Get detailed information about a specific Suno AI track.

    Args:
        track_id: The unique track identifier
    """
    return await _library.track_info(track_id)


@mcp.tool()
async def suno_track_extend(track_id: str, prompt: str, duration: int = 15) -> str:
    """Extend an existing Suno AI track with additional content.

    Args:
        track_id: The unique track identifier to extend
        prompt: Description of how to continue the track
        duration: Approximate extension length in seconds (default: 15)
    """
    return await _library.track_extend(track_id, prompt, duration)


@mcp.tool()
async def suno_track_remix(track_id: str, prompt: str, style: str = "") -> str:
    """Remix/cover an existing Suno AI track with a new prompt.

    Args:
        track_id: The unique track identifier to remix
        prompt: New description for the remix
        style: Optional new musical style
    """
    return await _library.track_remix(track_id, prompt, style)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
