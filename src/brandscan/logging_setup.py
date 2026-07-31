"""Structured logging and run-progress reporting.

A run over ~400 repositories is unattended and measured in hours, so the log is
the only window into it. Every record carries the repository it belongs to and
the running counts, so a log tailed midway answers "where is it and how is it
going" without needing the final report.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER_NAME = "brandscan"

# Libraries that log about a file they cannot name. Their records are re-routed
# rather than silenced: when a malformed file is genuinely puzzling, the
# parser's own message is the only real evidence, and discarding it leaves an
# operator with nothing.
THIRD_PARTY_LOGGERS = ("svglib", "reportlab")

_current_file: ContextVar[str] = ContextVar("brandscan_current_file", default="")


class _JsonFormatter(logging.Formatter):
    """Renders records as one JSON object per line, for the run log file."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for key, value in getattr(record, "context", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    """Human-readable console form: the message plus its context inline."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        context = getattr(record, "context", {})
        suffix = ""
        if context:
            suffix = "  " + " ".join(f"{k}={v}" for k, v in context.items())
        return f"{stamp} {record.levelname:<7} {record.getMessage()}{suffix}"


@contextmanager
def processing(path: str) -> Iterator[None]:
    """Name the file being processed, for records that cannot name it themselves.

    A third-party parser is handed bytes and knows nothing about where they came
    from, so its message arrives unattributable. Over ~400 repositories that is
    hundreds of lines an operator cannot act on. This is what supplies the
    missing half.
    """
    token = _current_file.set(path)
    try:
        yield
    finally:
        _current_file.reset(token)


class _RelayHandler(logging.Handler):
    """Forwards another library's records into the run log, at debug level.

    Debug because these are diagnostics about a file that is already being
    recorded as unread by the scan itself: the issue is the finding, this is the
    evidence behind it.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # a broken format string must not end a run
            message = record.msg if isinstance(record.msg, str) else "<unformattable>"
        debug(
            message,
            library=record.name,
            library_level=record.levelname,
            file=_current_file.get() or "unknown",
        )


def contain_third_party_loggers() -> None:
    """Route decoder and rasteriser diagnostics through the run log only.

    Without this, `svglib` writes straight to stderr once per unparseable file,
    naming none of them. Propagation is disabled so nothing reaches the root
    logger's last-resort handler, and their own handlers are replaced so nothing
    they installed at import time survives.

    The threshold is the libraries' own warning level, which is exactly what
    their last-resort handler would have shown. Nothing an operator could
    previously see is lost; what is gained is the filename and a home in the run
    log. Relaying their debug chatter as well would bury the run log under one
    entry per ignored SVG node across ~400 repositories.
    """
    handler = _RelayHandler()
    handler.setLevel(logging.WARNING)
    for name in THIRD_PARTY_LOGGERS:
        library = logging.getLogger(name)
        library.handlers.clear()
        library.addHandler(handler)
        library.setLevel(logging.WARNING)
        library.propagate = False


def configure_logging(log_file: Path | None = None, verbose: bool = False) -> logging.Logger:
    """Install console and (optionally) JSON-file handlers on the run logger."""
    contain_third_party_loggers()
    logger = logging.getLogger(LOGGER_NAME)
    # The logger passes everything and the handlers decide: the run log is the
    # record of what happened and wants the debug detail — including relayed
    # decoder diagnostics — while the console shows an operator only what they
    # can act on. Gating here instead would drop debug records before the file
    # handler that exists to keep them ever saw them.
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler(stream=sys.stderr)
    console.setFormatter(_ConsoleFormatter())
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(_JsonFormatter())
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def log(level: int, message: str, **context: Any) -> None:
    """Emit a record carrying arbitrary structured context."""
    get_logger().log(level, message, extra={"context": context})


def info(message: str, **context: Any) -> None:
    log(logging.INFO, message, **context)


def warning(message: str, **context: Any) -> None:
    log(logging.WARNING, message, **context)


def error(message: str, **context: Any) -> None:
    log(logging.ERROR, message, **context)


def debug(message: str, **context: Any) -> None:
    log(logging.DEBUG, message, **context)


@dataclass
class RunProgress:
    """Running counts across a run, logged at each repository boundary.

    The counters are the same categories the executive summary reconciles
    against the target set, so a tailed log and the final summary agree.
    """

    total: int = 0
    started: int = 0
    clean: int = 0
    with_findings: int = 0
    skipped: int = 0
    failed: int = 0
    _start_times: dict[str, float] = field(default_factory=dict, repr=False)

    def repo_started(self, slug: str) -> None:
        self.started += 1
        self._start_times[slug] = time.monotonic()
        info(
            "repository scan started",
            repository=slug,
            position=f"{self.started}/{self.total}",
        )

    def repo_finished(self, slug: str, outcome: str, findings: int = 0, reason: str = "") -> None:
        """Record a terminal outcome for one repository and log the new totals.

        ``outcome`` is one of ``clean``, ``findings``, ``skipped``, ``failed``.
        """
        if outcome == "clean":
            self.clean += 1
        elif outcome == "findings":
            self.with_findings += 1
        elif outcome == "skipped":
            self.skipped += 1
        elif outcome == "failed":
            self.failed += 1

        elapsed = time.monotonic() - self._start_times.pop(slug, time.monotonic())
        context: dict[str, Any] = {
            "repository": slug,
            "outcome": outcome,
            "findings": findings,
            "seconds": round(elapsed, 1),
            "done": f"{self.completed}/{self.total}",
            "clean": self.clean,
            "with_findings": self.with_findings,
            "skipped": self.skipped,
            "failed": self.failed,
        }
        if reason:
            context["reason"] = reason
        level = logging.WARNING if outcome in ("skipped", "failed") else logging.INFO
        log(level, "repository scan finished", **context)

    @property
    def completed(self) -> int:
        return self.clean + self.with_findings + self.skipped + self.failed
