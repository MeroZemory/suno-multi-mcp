"""Download tools for Suno MCP — CDN-based direct download."""

import json
import logging
import subprocess
import sys
from pathlib import Path

from ..browser.manager import BrowserManager
from ..exceptions import SunoError
from ..session.store import STORAGE_PATH

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr)

# Suno CDN URL pattern — works with session cookies for authenticated tracks.
CDN_BASE = "https://cdn1.suno.ai"


class DownloadTools:
    """Tools for downloading tracks from Suno AI."""

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    def _get_cookie_str(self) -> str:
        """Read session cookies from storage_state.json and return as Cookie header string."""
        if not STORAGE_PATH.exists():
            raise SunoError(
                f"No session file at {STORAGE_PATH}. Please login first with suno_login.",
                "NO_SESSION",
            )
        try:
            state = json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
            cookies = {c["name"]: c["value"] for c in state.get("cookies", [])}
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
        except Exception as e:
            raise SunoError(f"Failed to read session cookies: {e}", "SESSION_READ_ERROR")

    async def download_track(
        self,
        track_id: str,
        download_path: str = "downloads/",
        include_stems: bool = False,
    ) -> str:
        """Download a track from Suno AI by track ID using direct CDN URL.

        Uses `~/.suno-mcp/session/storage_state.json` cookies for authentication.
        The file is saved as `{track_id}.mp3` in the specified directory.
        """
        try:
            cookie_str = self._get_cookie_str()

            download_dir = Path(download_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            filepath = download_dir / f"{track_id}.mp3"

            url = f"{CDN_BASE}/{track_id}.mp3"
            logger.info("Downloading %s -> %s", url, filepath)

            result = subprocess.run(
                [
                    "curl", "-sL", "-o", str(filepath),
                    "-H", f"Cookie: {cookie_str}",
                    "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "-H", "Referer: https://suno.com/",
                    "--max-time", "120",
                    "--retry", "3",
                    url,
                ],
                capture_output=True,
                timeout=130,
            )

            if result.returncode != 0:
                raise SunoError(
                    f"curl failed (exit {result.returncode}): {result.stderr.decode(errors='replace')[:200]}",
                    "DOWNLOAD_CURL_ERROR",
                )

            size = filepath.stat().st_size if filepath.exists() else 0
            if size < 1024:
                # File too small — likely an error response (HTML/JSON) not an MP3
                content_preview = filepath.read_bytes()[:200].decode(errors="replace") if filepath.exists() else ""
                raise SunoError(
                    f"Downloaded file too small ({size} bytes) — likely auth error or invalid ID.\n"
                    f"Content preview: {content_preview}",
                    "DOWNLOAD_INVALID",
                )

            return (
                f"Download completed!\n"
                f"Track ID: {track_id}\n"
                f"Path: {filepath}\n"
                f"Size: {size:,} bytes ({size // 1024} KB)"
            )

        except SunoError:
            raise
        except Exception as e:
            logger.error("Download failed: %s", e)
            raise SunoError(f"Download failed: {e}", "DOWNLOAD_ERROR")
