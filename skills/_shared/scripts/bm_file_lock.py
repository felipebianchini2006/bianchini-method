#!/usr/bin/env python3
"""Lock exclusivo portátil para os arquivos de coordenação do método."""

from __future__ import annotations

import errno
import os

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercitado no subprocesso Windows simulado
    _fcntl = None
    import msvcrt as _msvcrt
else:
    _msvcrt = None


def _prepare_windows_lock(descriptor: int) -> None:
    if os.fstat(descriptor).st_size == 0:
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, b"\0")
        os.fsync(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)


def lock_exclusive_nonblocking(descriptor: int) -> None:
    if _fcntl is not None:
        _fcntl.flock(descriptor, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        return

    assert _msvcrt is not None
    _prepare_windows_lock(descriptor)
    try:
        _msvcrt.locking(descriptor, _msvcrt.LK_NBLCK, 1)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or getattr(
            error, "winerror", None
        ) in {33, 36}:
            raise BlockingIOError(errno.EAGAIN, "lock já adquirido") from error
        raise


def unlock(descriptor: int) -> None:
    if _fcntl is not None:
        _fcntl.flock(descriptor, _fcntl.LOCK_UN)
        return

    assert _msvcrt is not None
    os.lseek(descriptor, 0, os.SEEK_SET)
    _msvcrt.locking(descriptor, _msvcrt.LK_UNLCK, 1)
