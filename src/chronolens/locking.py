"""A tiny cross-process loop lock.

The loop pulls levers on a shared target, so two overlapping runs (say the UI
and the CLI at once) could fight each other. This is a best-effort file lock: an
atomic ``O_CREAT|O_EXCL`` create, with stale-lock detection so a crashed run
can't wedge the loop forever.
"""
from __future__ import annotations

import json
import os
import time


class LoopLock:
    def __init__(self, root: str, name: str = "loop.lock", stale_s: float = 240.0):
        os.makedirs(root, exist_ok=True)
        self.path = os.path.join(root, name)
        self.stale_s = stale_s
        self._held = False

    def _stale(self) -> bool:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                at = float(json.load(fh).get("at", 0))
            return (time.time() - at) > self.stale_s
        except Exception:
            return True  # unreadable/garbage lock -> treat as stale

    def acquire(self) -> bool:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if self._stale():
                try:
                    os.remove(self.path)
                except OSError:
                    return False
                return self.acquire()
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "at": time.time()}, fh)
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            try:
                os.remove(self.path)
            except OSError:
                pass
            self._held = False

    def __enter__(self) -> "LoopLock":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
