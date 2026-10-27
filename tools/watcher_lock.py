import errno
import os
from contextlib import contextmanager

from paths import WATCHER_LOCK_PATH


@contextmanager
def watcher_lock():
    WATCHER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Keep this file in place: deleting it could let processes lock different inodes.
    with WATCHER_LOCK_PATH.open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            yield False
            return

        try:
            yield True
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def watcher_is_running():
    with watcher_lock() as acquired:
        return not acquired
