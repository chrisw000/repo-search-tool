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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER_NAME = "brandscan"


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


def configure_logging(log_file: Path | None = None, verbose: bool = False) -> logging.Logger:
    """Install console and (optionally) JSON-file handlers on the run logger."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
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
