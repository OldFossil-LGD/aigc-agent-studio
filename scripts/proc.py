"""Every external process gets a deadline.

A hang is not a state any caller can handle, so a timeout becomes a normal
failed result (returncode = TIMEOUT_RC) instead of an exception. Callers already
branch on returncode, so their contracts do not change: they simply see a
failure instead of waiting forever.
"""
from __future__ import annotations

import subprocess

TIMEOUT_RC = -9
DEFAULT = 120
FFMPEG = 600
PLATFORM = 240


class _Result:
    """Shaped like subprocess.CompletedProcess for the fields callers read."""

    __slots__ = ("args", "returncode", "stdout", "stderr")

    def __init__(self, args, returncode, stdout, stderr):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(args, *, timeout=DEFAULT, **kwargs):
    kwargs.pop("timeout", None)
    try:
        return subprocess.run(args, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        wants_text = bool(kwargs.get("text") or kwargs.get("encoding")
                          or kwargs.get("universal_newlines"))
        shown = args if isinstance(args, str) else " ".join(str(x) for x in args[:3])
        message = "timed out after %ss: %s" % (timeout, shown)
        if wants_text:
            return _Result(args, TIMEOUT_RC, "", message)
        return _Result(args, TIMEOUT_RC, b"", message.encode("utf-8"))
