"""Tests for cross-platform file locking."""

import threading
import time
from pathlib import Path

import pytest
from claude_note.file_lock import file_lock, file_lock_exclusive, LockTimeout, write_locked, append_locked


class TestFileLock:
    def test_acquire_release(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        with file_lock(lock_path) as acquired:
            assert acquired is True
            assert lock_path.exists()

    def test_timeout_when_held(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        result = {"inner_acquired": None}

        def hold_lock():
            with file_lock(lock_path, timeout=5.0) as acquired:
                assert acquired
                time.sleep(2.0)

        t = threading.Thread(target=hold_lock)
        t.start()
        time.sleep(0.3)  # Let thread acquire lock

        with file_lock(lock_path, timeout=0.5) as acquired:
            result["inner_acquired"] = acquired

        t.join()
        assert result["inner_acquired"] is False

    def test_exclusive_raises_on_timeout(self, tmp_path):
        lock_path = tmp_path / "test.lock"

        def hold_lock():
            with file_lock_exclusive(lock_path, timeout=5.0):
                time.sleep(2.0)

        t = threading.Thread(target=hold_lock)
        t.start()
        time.sleep(0.3)

        with pytest.raises(LockTimeout):
            with file_lock_exclusive(lock_path, timeout=0.5):
                pass

        t.join()

    def test_write_locked(self, tmp_path):
        file_path = tmp_path / "data.txt"
        write_locked(file_path, "hello world")
        assert file_path.read_text() == "hello world"

    def test_append_locked(self, tmp_path):
        file_path = tmp_path / "data.txt"
        file_path.write_text("line1\n")
        append_locked(file_path, "line2\n")
        assert file_path.read_text() == "line1\nline2\n"
