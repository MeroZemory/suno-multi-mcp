"""Unit tests for SessionStore."""

import json
from pathlib import Path

import pytest

from suno_mcp.session.store import SessionStore


def test_session_store_not_exists(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "state.json")
    assert not store.exists()


def test_session_store_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = SessionStore(path=path)
    state = {"cookies": [{"name": "session", "value": "abc123"}], "origins": []}
    store.save(state)
    assert store.exists()
    loaded = store.load()
    assert loaded == state


def test_session_store_load_missing_returns_none(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "missing.json")
    assert store.load() is None


def test_session_store_load_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("NOT JSON", encoding="utf-8")
    store = SessionStore(path=path)
    result = store.load()
    assert result is None


def test_session_store_clear(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = SessionStore(path=path)
    store.save({"cookies": []})
    assert store.exists()
    store.clear()
    assert not store.exists()


def test_session_store_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "state.json"
    store = SessionStore(path=path)
    store.save({"cookies": []})
    assert path.exists()
