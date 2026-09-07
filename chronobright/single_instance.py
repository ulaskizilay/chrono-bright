"""Prevent multiple ChronoBright instances from fighting over brightness."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import TextIO

from chronobright import config
from chronobright.logger import get_logger

logger = get_logger(__name__)


class SingleInstanceLock:
    """Hold an exclusive lock file for the lifetime of the application."""

    def __init__(self, lock_path: Path | None = None) -> None:
        self._lock_path = lock_path if lock_path is not None else config.get_lock_path()
        self._handle: TextIO | None = None

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True on success, False if taken."""
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            # O_CREAT | O_EXCL fails if the file already exists.
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            handle: TextIO = os.fdopen(fd, "w")
            self._handle = handle
            self._lock_handle(handle)
            handle.write(str(os.getpid()))
            handle.flush()
            return True
        except FileExistsError:
            return False
        except OSError as exc:
            logger.warning("Could not create lock file %s: %s", self._lock_path, exc)
            # If we cannot lock, allow startup but warn — better than blocking.
            return True

    @staticmethod
    def _lock_handle(handle: TextIO) -> None:
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except ImportError:
            pass
        except OSError:
            pass
        with contextlib.suppress(ImportError, OSError, AttributeError):
            import fcntl

            flock = getattr(fcntl, "flock", None)
            lock_ex = getattr(fcntl, "LOCK_EX", 0)
            lock_nb = getattr(fcntl, "LOCK_NB", 0)
            if callable(flock):
                flock(handle.fileno(), lock_ex | lock_nb)

    def release(self) -> None:
        if self._handle is not None:
            with contextlib.suppress(OSError):
                self._handle.close()
            self._handle = None
        with contextlib.suppress(OSError):
            self._lock_path.unlink(missing_ok=True)
