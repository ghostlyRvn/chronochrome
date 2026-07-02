# chronochrome

Time-based color themes for your code editor.

Chronochrome swaps your editor's color theme automatically across the day —
a light theme in the morning, something dark for late-night hacking — based on
time-of-day blocks you configure. It is a small, stateless CLI run periodically
by your OS scheduler, **not** a background daemon and **not** an editor
extension.

v1 supports **Zed**. The architecture is adapter-based so other config-file
editors (VSCode, Sublime, Helix, …) can be added later without touching the
scheduling core.

## How it works

Chronochrome is not (and cannot be) a real editor extension — no editor's
extension system lets a plugin write the user's config file on a timer. Instead
it edits each editor's settings file directly. Editors like Zed watch their
config and reload live, so a theme change takes effect immediately.

`chronochrome apply` is stateless and idempotent: resolve the currently active
time block, and for each detected editor, patch its settings file **only if**
the mapped theme differs from what was last applied. The OS scheduler
(launchd on macOS, a `systemd --user` timer on Linux) invokes it every few
minutes — no long-running process to crash or miss a transition after sleep.

Zed's `settings.json` is JSONC (comments + trailing commas). Chronochrome
patches it as **text**, replacing only the `"theme"` value and leaving every
comment, blank line, and key order byte-for-byte intact.

## Install

Requires Python 3.11+.

```sh
pipx install git+https://github.com/ghostlyrvn/chronochrome
# or
uv tool install git+https://github.com/ghostlyrvn/chronochrome
```

Then register the scheduled job and write a starter config:

```sh
chronochrome install
```

This writes `~/.config/chronochrome/config.toml` (if absent) and installs the
launchd agent / systemd timer. Edit the config, then check it:

```sh
chronochrome validate
chronochrome apply --dry-run
```

## Configuration

`~/.config/chronochrome/config.toml`. Themes are mapped **per editor** — there
is no shared theme namespace. A block with no entry for an editor leaves that
editor untouched during that window.

```toml
check_interval_minutes = 5

[[blocks]]
name = "morning"
start = "06:00"
end = "11:00"
[blocks.themes]
zed = "One Light"

[[blocks]]
name = "night"
start = "21:00"
end = "06:00"      # wraps past midnight
[blocks.themes]
zed = "Ayu Dark"
```

Blocks may wrap past midnight (`end < start`). Gaps are allowed — Chronochrome
just leaves the theme untouched during an uncovered window. See
[`config.example.toml`](config.example.toml).

## Commands

| Command | What it does |
|---|---|
| `chronochrome install` | Write starter config (if absent) + register the scheduled job |
| `chronochrome uninstall` | Remove the scheduled job (config/state left in place) |
| `chronochrome apply` | Resolve the current block and patch each detected editor if needed |
| `chronochrome apply --dry-run` | Show what would change without writing |
| `chronochrome status` | Current block, per-editor themes, next transition, job state |
| `chronochrome validate` | Lint the config (overlaps, gaps, bad times, unmapped editors) |
| `chronochrome adapters` | List adapters and whether each is detected |

`apply` refuses to overwrite Zed's object-form `"theme"` (system light/dark
switching) unless you pass `--force`, since that conflicts with per-block
control.

## Development

```sh
uv sync            # or: pip install -e ".[dev]"
pytest
```

The Zed adapter test asserts that patching a commented fixture preserves every
comment and only touches the theme line.

## Non-goals

- Not a WASM/native editor extension; not in any editor's extension registry
- No Windows support in v1
- Only ever touches the one theme key each adapter owns
