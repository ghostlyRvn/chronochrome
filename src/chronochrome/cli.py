"""argparse entrypoint: install / uninstall / status / apply / validate / adapters."""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .adapters import AdapterError, all_adapters, detected_adapters
from .config import (
    DEFAULT_CONFIG_PATH,
    Config,
    ConfigError,
    format_minutes,
    load_config,
    validate_config,
)
from .scheduler import (
    minutes_until,
    next_transition,
    now_minutes,
    resolve_active_block,
)
from .state import DEFAULT_STATE_PATH, load_state


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #
def cmd_apply(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _eprint(f"chronochrome: config error: {exc}")
        return 2

    minute = now_minutes()
    resolution = resolve_active_block(config.blocks, minute)
    if not resolution.is_ok:
        if resolution.reason == "no-match":
            _eprint(
                f"chronochrome: no block active at {format_minutes(minute)}; "
                "leaving all editors untouched"
            )
        else:
            _eprint(
                f"chronochrome: multiple blocks active at {format_minutes(minute)} "
                "(config error); leaving all editors untouched"
            )
        # A gap is a normal, non-error condition; a multi-match is a config bug
        # but we still exit 0 so the scheduler doesn't spam failures.
        return 0

    block = resolution.block
    assert block is not None
    state = load_state(args.state)

    dry_run = args.dry_run
    changed_any = False
    exit_code = 0

    for adapter in detected_adapters():
        theme = block.theme_for(adapter.name)
        if theme is None:
            # No mapping for this editor in this block — leave it alone.
            continue

        last_theme = state.theme_for(adapter.name)
        if last_theme == theme:
            # Already applied — skip to avoid file-watch churn.
            continue

        if dry_run:
            print(
                f"[dry-run] {adapter.name}: would set theme to {theme!r} "
                f"(block {block.name!r}, currently {last_theme!r})"
            )
            changed_any = True
            continue

        try:
            adapter.set_theme(theme, force=args.force)
        except AdapterError as exc:
            _eprint(f"chronochrome: {adapter.name}: {exc}")
            exit_code = 1
            continue
        except OSError as exc:
            _eprint(f"chronochrome: {adapter.name}: failed to write settings: {exc}")
            exit_code = 1
            continue

        state.record(adapter.name, block.name, theme)
        changed_any = True
        print(f"{adapter.name}: theme set to {theme!r} (block {block.name!r})")

    if changed_any and not dry_run:
        state.save()

    if not changed_any and not dry_run:
        # Nothing to do is success and silent-ish (the scheduler calls this a lot).
        pass

    return exit_code


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def cmd_validate(args: argparse.Namespace) -> int:
    detected = [a.name for a in detected_adapters()]
    result = validate_config(args.config, detected_adapters=detected)

    for warning in result.warnings:
        _eprint(f"warning: {warning}")
    for error in result.errors:
        _eprint(f"error: {error}")

    if result.ok:
        print(f"chronochrome: config OK ({args.config})")
        return 0
    _eprint(f"chronochrome: config has {len(result.errors)} error(s)")
    return 1


# --------------------------------------------------------------------------- #
# adapters
# --------------------------------------------------------------------------- #
def cmd_adapters(args: argparse.Namespace) -> int:
    for adapter in all_adapters():
        present = adapter.detect()
        mark = "detected" if present else "not detected"
        print(f"{adapter.name:<10} {mark:<14} {adapter.settings_path()}")
    return 0


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def cmd_status(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _eprint(f"chronochrome: config error: {exc}")
        return 2

    minute = now_minutes()
    resolution = resolve_active_block(config.blocks, minute)

    print(f"time now:       {format_minutes(minute)}")
    if resolution.is_ok and resolution.block is not None:
        print(f"active block:   {resolution.block.name}")
    elif resolution.reason == "no-match":
        print("active block:   (none — in a gap; themes untouched)")
    else:
        print("active block:   (config error — multiple blocks match)")

    nxt = next_transition(config.blocks, minute)
    if nxt is not None:
        delta = minutes_until(nxt, minute)
        print(f"next change:    {format_minutes(nxt)} (in {delta} min)")

    print("themes per adapter:")
    state = load_state(args.state)
    detected = {a.name for a in detected_adapters()}
    active = resolution.block if resolution.is_ok else None
    for adapter in all_adapters():
        present = "detected" if adapter.name in detected else "not detected"
        target = active.theme_for(adapter.name) if active else None
        current = None
        if adapter.name in detected:
            current = adapter.get_current_theme()
        last = state.theme_for(adapter.name)
        print(
            f"  {adapter.name:<8} [{present}] "
            f"target={target!r} current={current!r} last-applied={last!r}"
        )

    # Is the scheduled job registered?
    print(f"scheduled job:  {_service_status()}")
    return 0


def _service_status() -> str:
    try:
        from . import service

        backend = service.get_service()
        return "registered" if backend.is_installed() else "not registered"
    except Exception as exc:  # UnsupportedPlatformError or import issue
        return f"unavailable ({exc})"


# --------------------------------------------------------------------------- #
# install / uninstall
# --------------------------------------------------------------------------- #
def _write_default_config(path: Path) -> bool:
    """Copy the packaged config.example.toml to ``path`` if absent. Returns
    True if it wrote a new file."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    example = _read_example_config()
    path.write_text(example, encoding="utf-8")
    return True


def _read_example_config() -> str:
    # Prefer the packaged copy; fall back to the repo root during development.
    try:
        return (
            resources.files("chronochrome")
            .joinpath("config.example.toml")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass
    repo_copy = Path(__file__).resolve().parents[2] / "config.example.toml"
    if repo_copy.exists():
        return repo_copy.read_text(encoding="utf-8")
    raise ConfigError("could not locate config.example.toml to install")


def cmd_install(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    wrote = _write_default_config(config_path)
    if wrote:
        print(f"wrote default config to {config_path}")
    else:
        print(f"config already exists at {config_path} (left unchanged)")

    # Read interval from config (fall back to default 5 if unreadable).
    interval = 5
    try:
        interval = load_config(config_path).check_interval_minutes
    except ConfigError as exc:
        _eprint(f"chronochrome: warning: {exc}; using default interval {interval} min")

    from . import service

    try:
        backend = service.get_service()
    except service.UnsupportedPlatformError as exc:
        _eprint(f"chronochrome: {exc}")
        return 1

    executable = service.chronochrome_executable()
    try:
        unit_path = backend.install(executable, interval)
    except Exception as exc:
        _eprint(f"chronochrome: failed to install scheduled job: {exc}")
        return 1
    print(f"installed scheduled job (every {interval} min): {unit_path}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    from . import service

    try:
        backend = service.get_service()
    except service.UnsupportedPlatformError as exc:
        _eprint(f"chronochrome: {exc}")
        return 1
    try:
        removed = backend.uninstall()
    except Exception as exc:
        _eprint(f"chronochrome: failed to remove scheduled job: {exc}")
        return 1
    if removed:
        print("removed scheduled job (config and state left in place)")
    else:
        print("no scheduled job was installed")
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chronochrome",
        description="Swap editor color themes based on time-of-day blocks.",
    )
    parser.add_argument("--version", action="version", version=f"chronochrome {__version__}")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"path to config.toml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE_PATH),
        help=f"path to state.json (default: {DEFAULT_STATE_PATH})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="write default config and register the scheduled job")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="remove the scheduled job (keeps config/state)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_apply = sub.add_parser("apply", help="resolve the current block and patch each detected editor")
    p_apply.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    p_apply.add_argument("--force", action="store_true", help="overwrite object-form/unexpected theme values")
    p_apply.set_defaults(func=cmd_apply)

    p_status = sub.add_parser("status", help="show current block, themes, next transition, job state")
    p_status.set_defaults(func=cmd_status)

    p_validate = sub.add_parser("validate", help="lint the config file")
    p_validate.set_defaults(func=cmd_validate)

    p_adapters = sub.add_parser("adapters", help="list registered adapters and detection state")
    p_adapters.set_defaults(func=cmd_adapters)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
