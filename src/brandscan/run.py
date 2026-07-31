"""The run: acquire, scan, report, roll up.

Everything here is arranged around one property — a run over hundreds of
repositories must not be endable by any single repository. Each one is acquired,
scanned, and reported inside its own failure boundary, and the checkpoint is
written after each so that an interruption costs one repository rather than the
whole run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from brandscan import tool_version
from brandscan.acquisition.checkpoint import Checkpoint
from brandscan.acquisition.clone import acquire
from brandscan.acquisition.enumerate_repos import enumerate_targets
from brandscan.acquisition.models import AcquisitionOutcome, AcquisitionResult, RepoTarget
from brandscan.acquisition.preflight import run_preflight
from brandscan.config.model import Config
from brandscan.findings import Finding
from brandscan.images.strategy import MatchStrategy, build_strategy
from brandscan.logging_setup import RunProgress, error, info, warning
from brandscan.paths import OutputLayout
from brandscan.report.markdown import write_repo_report
from brandscan.report.permalink import blob_permalink
from brandscan.report.summary import counts_reconcile, totals, write_summary
from brandscan.results import Provenance, RepoResult, RepoStatus
from brandscan.run_record import RunRecord
from brandscan.scan.image_search import scan_images
from brandscan.scan.text import scan_text


@dataclass
class RunOutcome:
    results: list[RepoResult] = field(default_factory=list)
    run_errors: list[str] = field(default_factory=list)
    summary_path: Path | None = None

    @property
    def totals(self) -> dict[str, int]:
        return totals(self.results)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _provenance(config: Config, strategy: MatchStrategy, result: AcquisitionResult) -> Provenance:
    return Provenance(
        tool_version=tool_version(),
        scanned_at=_now(),
        search_groups=[group.name for group in config.search_groups],
        reference_labels=config.reference_labels,
        similarity_threshold=config.similarity_threshold,
        threshold_was_defaulted=config.threshold_was_defaulted,
        matching_strategy=strategy.name,
        commit_sha=result.commit_sha,
        branch=result.branch,
    )


def _attach_permalinks(findings: list[Finding], target: RepoTarget, sha: str | None) -> None:
    for finding in findings:
        finding.permalink = blob_permalink(
            host=target.host,
            org=target.org,
            name=target.name,
            commit_sha=sha,
            path=finding.path,
            line=finding.line,
        )


def scan_repository(
    target: RepoTarget, config: Config, strategy: MatchStrategy, layout: OutputLayout
) -> RepoResult:
    """Acquire and scan one repository. Never raises for that repository's sake."""
    destination = layout.repo_dir(target.host, target.org, target.name)
    acquisition = acquire(target, destination)
    provenance = _provenance(config, strategy, acquisition)

    if acquisition.outcome is AcquisitionOutcome.SKIPPED:
        return RepoResult(
            target=target,
            status=RepoStatus.SKIPPED,
            provenance=provenance,
            reason=acquisition.reason,
        )
    if acquisition.outcome is AcquisitionOutcome.FAILED or acquisition.path is None:
        return RepoResult(
            target=target,
            status=RepoStatus.FAILED,
            provenance=provenance,
            reason=acquisition.reason or "acquisition failed for an unrecorded reason",
        )

    text_result = scan_text(acquisition.path, config.scope, config.search_groups)
    image_result = scan_images(
        acquisition.path, config.scope, strategy, text_result.embedded_images
    )

    findings = text_result.findings + image_result.findings
    findings.sort(key=lambda finding: finding.sort_key)
    _attach_permalinks(findings, target, acquisition.commit_sha)

    issues = text_result.issues + image_result.issues
    status = RepoStatus.FINDINGS if findings else RepoStatus.CLEAN

    return RepoResult(
        target=target,
        status=status,
        provenance=provenance,
        findings=findings,
        issues=issues,
        files_scanned=text_result.files_scanned,
        images_examined=image_result.images_examined,
    )


def _write_report(result: RepoResult, layout: OutputLayout) -> None:
    target = result.target
    markdown = layout.report_markdown(target.host, target.org, target.name)
    sidecar = layout.report_json(target.host, target.org, target.name)
    result.report_path = layout.summary_relative_link(target.host, target.org, target.name)
    write_repo_report(result, markdown, sidecar)


def _rehydrate(target: RepoTarget, layout: OutputLayout) -> RepoResult | None:
    """Recover a completed repository's result from the report it already wrote."""
    sidecar = layout.report_json(target.host, target.org, target.name)
    if not sidecar.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    try:
        result = RepoResult.from_dict(payload, target)
    except (KeyError, ValueError):
        return None
    result.report_path = layout.summary_relative_link(target.host, target.org, target.name)
    return result


def _outcome_for(result: RepoResult) -> str:
    return {
        RepoStatus.CLEAN: "clean",
        RepoStatus.FINDINGS: "findings",
        RepoStatus.SKIPPED: "skipped",
        RepoStatus.FAILED: "failed",
    }[result.status]


def _open_run_record(config: Config, layout: OutputLayout, mode: str) -> RunRecord:
    """Mark the run directory as holding a run in progress.

    A run being continued keeps the identity it was given when it first
    started; only its unfinished state is re-asserted, so that an interruption
    of the resumed run leaves it resumable in turn.
    """
    record = RunRecord.load(layout.run_record_file) or RunRecord(
        run_id=layout.run_id,
        started_at=_now(),
        tool_version=tool_version(),
        mode=mode,
        config_source=str(config.source_path) if config.source_path else None,
    )
    record.finished_at = None
    record.write(layout.run_record_file)
    return record


def _verify_coverage(targets: list[RepoTarget], layout: OutputLayout) -> list[str]:
    """Confirm every target repository actually has a report on disk.

    A missing report is the one failure this tool cannot report on itself, so
    it is checked explicitly rather than assumed from the loop completing.
    """
    missing: list[str] = []
    for target in targets:
        markdown = layout.report_markdown(target.host, target.org, target.name)
        sidecar = layout.report_json(target.host, target.org, target.name)
        if not markdown.is_file() or not sidecar.is_file():
            missing.append(target.slug)
    return missing


def execute_run(
    config: Config,
    layout: OutputLayout,
    resume: bool = True,
    refresh: bool = False,
    limit: int | None = None,
    skip_preflight: bool = False,
    mode: str = "both",
) -> RunOutcome:
    """Run a full scan and emit every artifact."""
    layout.bootstrap()
    record = _open_run_record(config, layout, mode)
    outcome = RunOutcome()

    if config.targets and not skip_preflight:
        run_preflight(config.targets)

    targets, enumeration_errors = enumerate_targets(config)
    outcome.run_errors.extend(enumeration_errors)

    if limit is not None:
        targets = targets[:limit]

    strategy = build_strategy(config.similarity_threshold)
    if config.reference_images:
        for failure in strategy.prepare(config.reference_images):
            message = f"reference image could not be loaded — {failure}"
            outcome.run_errors.append(message)
            warning("reference image failed to load", detail=failure)
        if not strategy.ready:
            outcome.run_errors.append(
                "no reference image could be loaded; image matching is disabled "
                "for this run"
            )
            warning("image matching disabled: no usable reference images")

    checkpoint = Checkpoint.load(layout.checkpoint_file)
    if not resume or refresh:
        checkpoint.clear()

    progress = RunProgress(total=len(targets))
    info(
        "run started",
        repositories=len(targets),
        groups=len(config.search_groups),
        references=len(config.reference_images),
        threshold=config.similarity_threshold,
        output=str(layout.root),
        run=layout.run_id,
    )

    for target in targets:
        if checkpoint.is_complete(target.key) and resume and not refresh:
            restored = _rehydrate(target, layout)
            if restored is not None:
                outcome.results.append(restored)
                progress.repo_started(target.slug)
                progress.repo_finished(
                    target.slug,
                    _outcome_for(restored),
                    findings=len(restored.findings),
                    reason="restored from checkpoint",
                )
                continue
            # The checkpoint claims completion but the report is gone; scan it
            # again rather than leave a hole in the target set.
            warning("checkpointed report missing; rescanning", repository=target.slug)

        progress.repo_started(target.slug)
        try:
            result = scan_repository(target, config, strategy, layout)
        except Exception as exc:  # one repository must never end the run
            error(
                "repository scan raised",
                repository=target.slug,
                reason=f"{type(exc).__name__}: {exc}",
            )
            result = RepoResult(
                target=target,
                status=RepoStatus.FAILED,
                provenance=Provenance(tool_version=tool_version(), scanned_at=_now()),
                reason=f"unexpected error during scan: {type(exc).__name__}: {exc}",
            )

        try:
            _write_report(result, layout)
        except OSError as exc:
            error("report could not be written", repository=target.slug, reason=str(exc))
            outcome.run_errors.append(f"{target.slug}: report could not be written: {exc}")

        outcome.results.append(result)
        checkpoint.record(
            target.key,
            {
                "status": result.status.value,
                "findings": len(result.findings),
                "commit_sha": result.provenance.commit_sha,
                "completed_at": _now(),
            },
        )
        progress.repo_finished(
            target.slug,
            _outcome_for(result),
            findings=len(result.findings),
            reason=result.reason,
        )

    missing = _verify_coverage(targets, layout)
    if missing:
        message = "repositories with no report on disk: " + ", ".join(missing)
        outcome.run_errors.append(message)
        error("report coverage incomplete", missing=len(missing))

    counts = totals(outcome.results)
    if not counts_reconcile(counts):
        outcome.run_errors.append(
            "run totals do not reconcile against the target set; some repository "
            "is unaccounted for"
        )

    write_summary(
        outcome.results,
        outcome.run_errors,
        config,
        layout.summary_file,
        layout.summary_json_file,
        layout.summary_html_file,
    )
    # The Markdown stays the run's nominal summary; the HTML is the same
    # document for a reader, not a different artifact to point tooling at.
    outcome.summary_path = layout.summary_file

    # Reaching here is what "finished" means: repositories that failed and
    # run-level errors are results of a completed run, not an incomplete one.
    record.finished_at = _now()
    record.write(layout.run_record_file)

    info(
        "run finished",
        scanned=counts["scanned"],
        clean=counts["clean"],
        with_findings=counts["with_findings"],
        skipped=counts["skipped"],
        failed=counts["failed"],
        findings=counts["findings"],
        summary=str(layout.summary_file),
    )
    return outcome
