#!/usr/bin/env python3
"""Local write mutex for a single shared Dolt clone.

Topology this supports: ONE clone on a host, N agents (separate processes) writing
to it. Concurrent server-less writes to one clone fail with
`cannot update manifest: ...` — Dolt's storage manifest is single-writer. This
serializes them.

Uses fcntl.flock on a lockfile inside the clone, which gives three properties a
row-based lease cannot:
  1. cross-PROCESS (agents are separate processes, not threads)
  2. auto-released by the kernel if the holder crashes or is SIGKILLed
  3. zero network cost

Scope: one host / one filesystem. It says nothing across machines — that is
push-as-CAS's job (poc/test_serverless_lock.py).
"""
from __future__ import annotations

import errno
import fcntl
import os
import random
import time
from contextlib import contextmanager
from pathlib import Path

LOCKFILE = ".fa-write.lock"


class CloneLockTimeout(RuntimeError):
    pass


@contextmanager
def clone_write_lock(clone_dir: str | Path, timeout: float = 60.0,
                     poll: float = 0.005):
    """Hold an exclusive write lock on `clone_dir` for the duration of the block.

    Polls a non-blocking flock so a timeout is enforceable (a plain blocking
    LOCK_EX cannot time out, and a wedged holder would hang every agent forever).
    """
    path = Path(clone_dir) / LOCKFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise CloneLockTimeout(
                        f"could not acquire clone write lock on {path} in {timeout}s")
                # jittered backoff so N waiters do not thunder
                time.sleep(poll + random.random() * poll)
        # Record the holder for debugging; not used for correctness.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()} {time.time():.3f}\n".encode())
        os.fsync(fd)
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def is_locked(clone_dir: str | Path) -> bool:
    """True if another process currently holds the lock. Race-y by nature —
    for diagnostics only, never for control flow."""
    path = Path(clone_dir) / LOCKFILE
    if not path.exists():
        return False
    fd = os.open(str(path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)
