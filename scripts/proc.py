"""Every external process gets a deadline.

A hang is not a state any caller can handle, so a timeout becomes a normal
failed result (returncode = TIMEOUT_RC) instead of an exception. Callers already
branch on returncode, so their contracts do not change: they simply see a
failure instead of waiting forever.
"""
from __future__ import annotations

import os
import signal
import subprocess

TIMEOUT_RC = -9
DEFAULT = 120
FFMPEG = 600
PLATFORM = 240
CLEANUP_TIMEOUT = 1


class _Result:
    """Shaped like subprocess.CompletedProcess for the fields callers read."""

    __slots__ = ("args", "returncode", "stdout", "stderr")

    def __init__(self, args, returncode, stdout, stderr):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stop_tree(process, owns_group):
    """Stop descendants before closing the parent that owns their output pipes."""
    if os.name == "nt":
        taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                "System32", "taskkill.exe")
        try:
            subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           timeout=CLEANUP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif owns_group:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def run(args, *, timeout=DEFAULT, input=None, capture_output=False, check=False, **kwargs):
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used")
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    # A private POSIX session lets timeout cleanup address the whole child group.
    # Explicit session/group choices retain their subprocess.Popen semantics.
    owns_group = False
    if os.name != "nt":
        if "start_new_session" not in kwargs and "process_group" not in kwargs:
            kwargs["start_new_session"] = True
        owns_group = kwargs.get("start_new_session", False)
    process = subprocess.Popen(args, **kwargs)
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_tree(process, owns_group)
        try:
            process.communicate(timeout=CLEANUP_TIMEOUT)
        except subprocess.TimeoutExpired:
            # A detached child can retain a pipe after the original PID exits.
            # Do not wait indefinitely for that pipe, including in Popen.__exit__.
            process.wait(timeout=CLEANUP_TIMEOUT)
        wants_text = bool(kwargs.get("text") or kwargs.get("encoding")
                          or kwargs.get("universal_newlines"))
        shown = args if isinstance(args, str) else " ".join(str(x) for x in args[:3])
        message = "timed out after %ss: %s" % (timeout, shown)
        if wants_text:
            return _Result(args, TIMEOUT_RC, "", message)
        return _Result(args, TIMEOUT_RC, b"", message.encode("utf-8"))
    except BaseException:
        _stop_tree(process, owns_group)
        process.wait(timeout=CLEANUP_TIMEOUT)
        raise
    if check and process.returncode:
        raise subprocess.CalledProcessError(process.returncode, args,
                                            output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
