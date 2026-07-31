"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from brandscan import TOOL_NAME, tool_version
from brandscan.acquisition.clone import normalise_remote
from brandscan.acquisition.commands import CommandError, git_origin_url
from brandscan.acquisition.preflight import PreflightError
from brandscan.config.loader import ConfigError, load_config
from brandscan.config.model import Config, ExternalRepo, Target
from brandscan.logging_setup import configure_logging, info, warning
from brandscan.paths import select_layout
from brandscan.run import execute_run

MODE_MANAGED = "managed"
MODE_EXTERNAL = "external"
MODE_BOTH = "both"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=(
            "Find traces of an old brand across many repositories, by image "
            "content and by text pattern. Reports only; never edits a scanned "
            "repository."
        ),
    )
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {tool_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="run a scan and emit reports")
    scan.add_argument("--config", type=Path, required=True, help="path to the scan config")
    scan.add_argument("--output", type=Path, help="output directory (overrides the config)")
    scan.add_argument(
        "--mode",
        choices=[MODE_MANAGED, MODE_EXTERNAL, MODE_BOTH],
        default=MODE_BOTH,
        help=(
            "which repository sources to use: managed clones the tool owns and "
            "may reset, external pre-cloned directories it never modifies, or "
            "both (default)"
        ),
    )
    scan.add_argument(
        "--external-root",
        type=Path,
        help=(
            "treat every immediate subdirectory of this path as an external "
            "clone, deriving its host and organisation from its origin remote"
        ),
    )
    scan.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="HOST/ORG/NAME",
        help=(
            "scan only this repository; repeatable. Narrows a configured target "
            "when given as ORG/NAME, or adds one outright as HOST/ORG/NAME. "
            "Intended for trial runs over a chosen validation set."
        ),
    )
    scan.add_argument(
        "--run-id",
        metavar="NAME",
        help=(
            "write to this run directory under the output directory, creating "
            "it if it does not exist. Without it, an unfinished run is "
            "continued and a finished one is left alone in favour of a new run"
        ),
    )
    scan.add_argument("--threshold", type=int, help="override the similarity threshold")
    scan.add_argument("--limit", type=int, help="scan at most this many repositories")
    scan.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore any existing checkpoint and scan every repository again",
    )
    scan.add_argument(
        "--refresh",
        action="store_true",
        help="re-acquire and re-scan repositories already completed in an earlier run",
    )
    scan.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip the multi-host authentication preflight (for offline testing)",
    )
    scan.add_argument("--verbose", action="store_true", help="log at debug level")

    validate = subparsers.add_parser(
        "validate-config", help="validate a scan config without acquiring anything"
    )
    validate.add_argument("--config", type=Path, required=True)

    return parser


def _discover_external_root(root: Path) -> list[ExternalRepo]:
    """Build external entries from every git repository directly under a root.

    Host and organisation come from each directory's own origin remote, so the
    permalinks in its report point at the right place without the operator
    restating what git already knows.
    """
    discovered: list[ExternalRepo] = []
    if not root.is_dir():
        raise ConfigError("--external-root", f"directory not found: {root}")

    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / ".git").exists():
            continue
        try:
            origin = git_origin_url(child)
        except CommandError:
            warning("external clone has no origin remote; skipping", path=str(child))
            continue
        normalised = normalise_remote(origin)
        if normalised is None:
            warning("external clone origin not understood; skipping", path=str(child))
            continue
        host, path = normalised
        org, _, name = path.rpartition("/")
        if not org or not name:
            warning("external clone origin has no owner; skipping", path=str(child))
            continue
        discovered.append(ExternalRepo(host=host, org=org, name=name, path=child))
    return discovered


def _apply_repo_selection(config: Config, selections: list[str]) -> None:
    """Narrow the run to repositories named on the command line.

    `ORG/NAME` narrows an existing configured target, so the host and its
    options carry over. `HOST/ORG/NAME` is self-contained and adds a target
    when none matches, which is what makes a trial run possible against a
    config that otherwise names whole organisations.
    """
    if not selections:
        return

    wanted: dict[tuple[str | None, str], list[str]] = {}
    for raw in selections:
        parts = [part for part in raw.strip().strip("/").split("/") if part]
        if len(parts) == 2:
            host, org, name = None, parts[0], parts[1]
        elif len(parts) == 3:
            host, org, name = parts[0], parts[1], parts[2]
        else:
            raise ConfigError(
                "--repo",
                f"expected ORG/NAME or HOST/ORG/NAME (got {raw!r})",
            )
        wanted.setdefault((host, org), []).append(name)

    narrowed: list[Target] = []
    for (host, org), names in wanted.items():
        match = next(
            (
                t
                for t in config.targets
                if t.org == org and (host is None or t.host == host)
            ),
            None,
        )
        if match is not None:
            narrowed.append(replace(match, repos=tuple(names)))
            continue
        if host is None:
            configured = ", ".join(sorted({t.label for t in config.targets})) or "none"
            raise ConfigError(
                "--repo",
                f"no configured target for organisation {org!r}; give the host as "
                f"HOST/{org}/NAME, or add the target to the config. "
                f"Configured targets: {configured}",
            )
        narrowed.append(Target(host=host, org=org, repos=tuple(names)))

    # Anything not named is out of scope for this run; that is the point.
    config.targets = narrowed
    config.external_repositories = []


def _apply_mode(config: Config, mode: str) -> None:
    """Restrict the run to one acquisition posture."""
    if mode == MODE_MANAGED:
        config.external_repositories = []
    elif mode == MODE_EXTERNAL:
        config.targets = []


def _run_scan(args: argparse.Namespace) -> int:
    # The command line can supply the repositories itself, so the file is not
    # required to name any until those flags have been folded in.
    config = load_config(
        args.config,
        require_repository_source=not (args.external_root or args.repo),
    )

    if args.repo:
        _apply_repo_selection(config, args.repo)

    if args.external_root:
        config.external_repositories = list(config.external_repositories) + _discover_external_root(
            args.external_root.expanduser().resolve()
        )

    _apply_mode(config, args.mode)

    if args.output:
        config.output_dir = args.output.expanduser().resolve()
    if args.threshold is not None:
        if args.threshold < 0:
            raise ConfigError("--threshold", "must be a non-negative integer")
        config.similarity_threshold = args.threshold
        config.threshold_was_defaulted = False

    if not config.targets and not config.external_repositories:
        raise ConfigError(
            "--mode",
            f"mode {args.mode!r} leaves no repository to scan; the configuration "
            "has none of that kind",
        )

    # Selected before logging is configured, because the log belongs to the run
    # directory this chooses.
    layout = select_layout(
        config.output_dir,
        run_id=args.run_id,
        force_new=args.no_resume or args.refresh,
    )
    layout.bootstrap()
    configure_logging(log_file=layout.log_file, verbose=args.verbose)
    info(
        "brandscan starting",
        version=tool_version(),
        config=str(config.source_path or args.config),
        mode=args.mode,
        run=layout.run_id,
    )
    print(f"Run: {layout.run_dir}")

    outcome = execute_run(
        config=config,
        layout=layout,
        resume=not args.no_resume,
        refresh=args.refresh,
        limit=args.limit,
        skip_preflight=args.skip_preflight,
        mode=args.mode,
    )

    counts = outcome.totals
    print(f"\nExecutive summary: {outcome.summary_path}")
    print(
        f"  targeted {counts['targeted']} | scanned {counts['scanned']} "
        f"(clean {counts['clean']}, with findings {counts['with_findings']}) | "
        f"skipped {counts['skipped']} | failed {counts['failed']}"
    )
    print(f"  {counts['findings']} finding(s) total")
    if outcome.run_errors:
        print(f"  {len(outcome.run_errors)} run-level error(s); see the summary")

    # A run that could not read some repositories still produced its reports;
    # the non-zero exit is what makes that visible to a scheduler.
    return 1 if counts["failed"] or outcome.run_errors else 0


def _run_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"Configuration is valid: {config.source_path}")
    print(f"  targets: {len(config.targets)}")
    for target in config.targets:
        print(f"    - {target.label}")
    print(f"  external repositories: {len(config.external_repositories)}")
    print(f"  search-groups: {', '.join(g.name for g in config.search_groups) or 'none'}")
    print(
        f"  reference images: {len(config.reference_images)} "
        f"({', '.join(config.reference_labels) or 'none'})"
    )
    source = "default" if config.threshold_was_defaulted else "configured"
    print(f"  similarity threshold: {config.similarity_threshold} ({source})")
    print(f"  output directory: {config.output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(verbose=getattr(args, "verbose", False))

    try:
        if args.command == "scan":
            return _run_scan(args)
        if args.command == "validate-config":
            return _run_validate(args)
    except ConfigError as exc:
        print(f"Configuration error in {exc.field}: {exc.message}", file=sys.stderr)
        return 2
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Progress is checkpointed; re-run the same command to "
            "resume from where it stopped.",
            file=sys.stderr,
        )
        return 130

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
