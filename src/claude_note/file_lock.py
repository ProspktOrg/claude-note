"""Cross-platform file locking for claude-note.

Provides FileLock context manager that works on both Unix (fcntl) and Windows (msvcrt).
"""

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Platform-specific imports
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class LockTimeout(Exception):
    """Raised when a lock cannot be acquired within the timeout period."""
    pass


@contextmanager
def file_lock(lock_path: Path, timeout: float = 30.0, exclusive: bool = True) -> Iterator[bool]:
    """
    Cross-platform file locking context manager.

    Args:
        lock_path: Path to the lock file
        timeout: Maximum seconds to wait for lock
        exclusive: If True, acquire exclusive lock; otherwise shared

    Yields:
        True if lock was acquired
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    acquired = False
    start_time = time.time()

    try:
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT, 0o644)

        while time.time() - start_time < timeout:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                    fcntl.flock(fd, flag | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError, IOError):
                time.sleep(0.1)

        yield acquired

    finally:
        if fd is not None:
            if acquired:
                try:
                    if sys.platform == "win32":
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
            os.close(fd)


@contextmanager
def file_lock_exclusive(lock_path: Path, timeout: float = 30.0) -> Iterator[None]:
    """
    Acquire exclusive file lock, raising LockTimeout on failure.

    Unlike file_lock(), this raises instead of yielding False.
    """
    with file_lock(lock_path, timeout=timeout, exclusive=True) as acquired:
        if not acquired:
            raise LockTimeout(f"Could not acquire lock on {lock_path} within {timeout}s")
        yield


def write_locked(file_path: Path, content: str, lock_dir: Path = None, timeout: float = 30.0) -> None:
    """
    Write to a file with locking. Uses atomic write (temp + rename).

    Args:
        file_path: File to write
        content: Content to write
        lock_dir: Directory for lock files (defaults to file_path.parent)
        timeout: Lock timeout in seconds
    """
    import hashlib

    if lock_dir is None:
        lock_dir = file_path.parent

    path_hash = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
    lock_path = lock_dir / f".{path_hash}.lock"

    with file_lock_exclusive(lock_path, timeout=timeout):
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)


def append_locked(file_path: Path, content: str, timeout: float = 30.0) -> None:
    """
    Append to a file with cross-platform locking.

    Args:
        file_path: File to append to
        content: Content to append
        timeout: Lock timeout in seconds
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    start_time = time.time()
    acquired = False

    try:
        while time.time() - start_time < timeout:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError, IOError):
                time.sleep(0.1)

        if not acquired:
            raise LockTimeout(f"Could not acquire lock on {file_path} within {timeout}s")

        os.write(fd, content.encode("utf-8"))
    finally:
        if acquired:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
        os.close(fd)
