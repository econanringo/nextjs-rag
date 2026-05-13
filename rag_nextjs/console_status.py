"""
ターミナル用スピナーと進捗表示（回答の標準出力とは分離し stderr に表示）。
TTY でない場合はアニメーションの代わりに行単位のメッセージを出します。
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from collections.abc import Callable
from typing import IO, TypeVar

_SPIN_FRAMES_ASCII = "|/-\\"
_SPIN_FRAMES_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠇⠏"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _use_unicode_spinner(stream: IO[str]) -> bool:
    enc = getattr(stream, "encoding", None)
    if isinstance(enc, str):
        n = enc.lower().replace("_", "")
        if n in {"utf-8", "utf8"}:
            return True
    return False


def _format_status_line(prefix: str, main: str, detail: str) -> str:
    cols = shutil.get_terminal_size(fallback=(88, 24)).columns
    width = max(40, cols - 2)
    body = f"{prefix}  {main}"
    if detail.strip():
        body = f"{body}  ·  {detail.strip()}"
    if len(body) > width:
        body = body[: width - 1] + "…"
    return body


class _SpinnerRunner(threading.Thread):
    def __init__(self, out: IO[str], frames: str) -> None:
        super().__init__(daemon=True)
        self._out = out
        self._frames = frames
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._main = ""
        self._detail = ""

    def configure(self, main: str, detail: str = "") -> None:
        with self._lock:
            self._main = main
            self._detail = detail

    def halt(self) -> None:
        self._stop.set()

    def run(self) -> None:
        i = 0
        while not self._stop.wait(0.09):
            with self._lock:
                main, detail = self._main, self._detail
            symbol = self._frames[i % len(self._frames)]
            i += 1
            line = _format_status_line(symbol, main, detail)
            self._out.write(f"\r{line}\x1b[K")
            self._out.flush()

    def wipe(self) -> None:
        self._out.write("\r\x1b[K")
        self._out.flush()


class ConsoleProgress:
    """MCP・取得フェーズ用プログレス表示。"""

    def __init__(self, *, enabled: bool, stream: IO[str] | None = None) -> None:
        self._out: IO[str] = stream if stream is not None else sys.stderr
        is_tty = getattr(self._out, "isatty", lambda: False)()
        spinner_on = _env_bool("RAG_SPINNER", True)
        force = _env_bool("RAG_SPINNER_FORCE", False)
        frames = _SPIN_FRAMES_UNICODE if _use_unicode_spinner(self._out) else _SPIN_FRAMES_ASCII
        self._enabled = enabled
        self._animate = enabled and spinner_on and (is_tty or force)
        self._runner: _SpinnerRunner | None = _SpinnerRunner(self._out, frames) if self._animate else None
        self._started = False
        self._last_plain: tuple[str, str] | None = None

    def start(self, main: str, detail: str = "") -> None:
        self.phase(main, detail)
        if not self._enabled or self._started:
            return
        self._started = True
        if self._runner:
            self._runner.configure(main, detail)
            self._runner.start()

    def phase(self, main: str, detail: str = "") -> None:
        if not self._enabled:
            return
        if self._runner and self._started and self._runner.is_alive():
            self._runner.configure(main, detail)
            return
        if not self._animate:
            key = (main, detail)
            if key != self._last_plain:
                self._last_plain = key
                suffix = f" ({detail})" if detail.strip() else ""
                self._out.write(f"[nextjs-rag]{suffix} {main}\n")
                self._out.flush()

    def stop_clear(self) -> None:
        if not self._enabled:
            return
        if self._runner and self._started:
            self._runner.halt()
            self._runner.join(timeout=3.0)
            self._runner.wipe()
            self._started = False


T = TypeVar("T")


def run_sync_blocking_with_spinner(
    fn: Callable[[], T],
    *,
    out: IO[str],
    main: str,
    detail: str = "",
    enabled: bool,
) -> T:
    """同期ブロッキング処理（例: 最初のチャンクまで）を別スレッドのスピナー付きで包む。"""
    if not enabled:
        return fn()

    is_tty = getattr(out, "isatty", lambda: False)()
    spinner_on = _env_bool("RAG_SPINNER", True)
    force = _env_bool("RAG_SPINNER_FORCE", False)
    if not spinner_on or (not is_tty and not force):
        out.write(f"[nextjs-rag] {main}{(' · ' + detail) if detail.strip() else ''}\n")
        out.flush()
        return fn()

    frames = _SPIN_FRAMES_UNICODE if _use_unicode_spinner(out) else _SPIN_FRAMES_ASCII
    stop = threading.Event()

    def worker() -> None:
        i = 0
        while not stop.wait(0.09):
            symbol = frames[i % len(frames)]
            i += 1
            line = _format_status_line(symbol, main, detail)
            out.write(f"\r{line}\x1b[K")
            out.flush()

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    try:
        return fn()
    finally:
        stop.set()
        th.join(timeout=3.0)
        out.write("\r\x1b[K")
        out.flush()
