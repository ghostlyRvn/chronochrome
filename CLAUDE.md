# CLAUDE.md

## Project: Chronochrome

A tool that automatically swaps color themes based on user-configurable
time-of-day blocks. Zed is the first supported editor; the architecture is
designed so other config-file-based editors (VSCode, Helix, Sublime Text,
etc.) can be added later as adapters without touching the core scheduling
logic.

---

## Context Claude needs before touching this repo

**This is not, and cannot be, a real Zed extension** (and the equivalent is
true for VSCode/Sublime/etc. extension systems too). Zed's official extension
system is WASM-based and event-driven — extensions can provide language
servers, themes, icon themes, slash commands, MCP servers, and debuggers, but
they are only invoked when the editor calls into them (e.g. opening a file).
There is no capability for a background process, a timer, or writing to the
user's config file on a schedule. Do not attempt to build this as a
`zed_extension_api` WASM extension, a VSCode extension activation event, etc.
— it's the wrong tool for this job in every editor's extension model, for the
same underlying reason.

Instead, Chronochrome is a **standalone external tool** that edits each
target editor's settings file directly. Editors like Zed and VSCode watch
their config file and reload live, so this works well in practice — it just
isn't distributed through any editor's official extension registry.

---

## Architecture decision: scheduled script, not a daemon

**Decision:** Chronochrome ships as a small idempotent CLI command
(`chronochrome apply`) that is invoked periodically by the OS's native
scheduler:
- macOS: a `launchd` user agent using `StartInterval`
- Linux: a `systemd --user` timer unit

**Not** a long-running daemon with an internal sleep loop.

**Why:** A persistent process has to handle its own crash recovery, restart
on boot, and correctly notice when the machine slept through a scheduled
transition. `launchd`/`systemd` already solve all of that. Each invocation of
`chronochrome apply` is stateless and fast: resolve the current time block,
compare to the last-applied theme *per editor*, patch each editor's file only
if something changed, exit.

Default check interval: every 5 minutes (configurable in `config.toml`).

---

## Editor adapter architecture

This is the part that makes the tool editor-agnostic. `scheduler.py`,
`config.py`, and `state.py` know nothing about any specific editor — they
only reason about "time blocks" and "logical theme names." All editor-specific
knowledge lives behind one interface:

```python
class EditorAdapter(Protocol):
    name: str                              # "zed", "vscode", "helix", ...
    def detect(self) -> bool               # is this editor installed / config present?
    def settings_path(self) -> Path
    def get_current_theme(self) -> str | None
    def set_theme(self, theme_name: str) -> None   # format-safe patch
```

`chronochrome apply` loops over every **registered and detected** adapter and,
for each one, applies the theme mapped to that editor for the currently
active block (see config schema below). An editor with no mapping for the
active block is skipped, not errored.

**v1 ships exactly one adapter: Zed.** The interface above exists so a second
adapter can be added later as a self-contained module, without changes to
scheduling, config parsing, or state tracking. Which editor that is hasn't
been decided yet — don't build a second adapter speculatively; get Zed solid
first and let the interface prove itself against one real implementation
before generalizing further.

**Known variation across editors** (for whenever a second adapter gets built):

| Editor | Config path (macOS/Linux) | Format | Theme key |
|---|---|---|---|
| Zed | `~/.config/zed/settings.json` | JSONC | `"theme"` |
| VSCode | `~/Library/Application Support/Code/User/settings.json` / `~/.config/Code/User/settings.json` | JSONC | `"workbench.colorTheme"` |
| Sublime Text | `.../Packages/User/Preferences.sublime-settings` | JSON-with-comments | `"color_scheme"` |
| Helix | `~/.config/helix/config.toml` | TOML | `"theme"` |

The JSONC editors (Zed, VSCode, Sublime) can share a common regex-based
patch helper (`adapters/_jsonc_patch.py`) — locate the top-level key, replace
only its value, leave comments/formatting/key order untouched, write via
temp-file + atomic rename. A TOML-based editor like Helix needs a different
strategy: `tomlkit` (not stdlib `tomllib`, which is read-only) round-trips
TOML while preserving comments and formatting, so it plays the same role for
TOML that the regex patch plays for JSONC. `tomlkit` is not a dependency of
v1 — only pull it in when a TOML-based adapter is actually built.

**Edge case worth remembering:** this whole model assumes "config file with a
static theme key." Something like Neovim doesn't fit that shape — colorscheme
is normally set via a line of Lua/Vimscript in `init.lua`, not a declarative
key. Not impossible to support later (e.g. generating a small file that gets
`require`'d), but it's a materially different kind of adapter, not just
another row in the table above. Don't assume the `EditorAdapter` interface
covers it without revisiting `set_theme`'s contract first.

---

## Terminal emulator adapters (planned — Ghostty is next)

v1 is Zed only. The **second adapter is a terminal emulator: Ghostty** — chosen
because Ricardo actually runs it (alongside Zed), not because it's the easiest
fit. Terminal configs were surveyed against the same three requirements the Zed
adapter leans on: **(a)** a plain-text config file, **(b)** a single theme
selector — a named theme or one `include`/`import` line, not ~20 expanded color
keys — and **(c)** the app live-reloads when the file changes on disk.

_Verified against official docs/source, 2026-07. Versions move — re-check the
reload defaults before building, since that column is what changes most._

| Terminal | Selector | Config format | Auto-reload on file change | Platforms | Fit |
|---|---|---|---|---|---|
| WezTerm | `color_scheme = 'X'` (named) | Lua | yes (default) | mac/Linux/Win | clean |
| Rio | `theme = "X"` (named) | TOML | yes (default) | mac/Linux/Win | clean |
| Alacritty | `import = ["…/X.toml"]` (file) | TOML | yes (`live_config_reload`) | mac/Linux/Win | clean |
| Kitty | `include current-theme.conf` (file) | custom `key value` | yes since 0.47 (`auto_reload_config`) | mac/Linux | clean |
| **Ghostty** | `theme = X` (named, 300+) | custom `key = value` | **no** — keybind / `SIGUSR2` | mac/Linux | needs reload hook |
| foot | `include=…` (file) | INI | no (SIGUSR1/2 only toggle two themes) | Linux/Wayland | needs reload hook |
| iTerm2 / Apple Terminal | color-preset keys | binary plist | no (app owns prefs) | macOS | doesn't fit |
| GNOME Terminal | palette keys | dconf DB (binary) | n/a (not a file) | Linux | doesn't fit |
| Hyper | 16 color keys + npm plugins | JavaScript | yes | mac/Linux/Win | no single selector |
| Tabby | inline color object | YAML | undocumented | mac/Linux/Win | no bare-name selector |

(Windows Terminal is a perfect fit — `"colorScheme"` in JSONC, live-reload on
save — but is Windows-only, so out of scope until Windows is.)

### Ghostty adapter specifics (verified)

- **Config path:** Linux `~/.config/ghostty/config`
  (`$XDG_CONFIG_HOME/ghostty/config`). macOS
  `~/Library/Application Support/com.mitchellh.ghostty/config` — note macOS
  **also** reads `~/.config/ghostty/config`, and the Application Support file
  wins on conflict. The adapter must patch the file Ghostty actually loads.
- **Format:** custom `key = value`, one directive per line, `#` comments. **Not**
  JSONC/TOML — it cannot reuse `_jsonc_patch.py`.
- **Theme key:** a single `theme = <name>`; ~300+ bundled themes
  (`ghostty +list-themes`). The name is written **unquoted** and may contain
  spaces: `theme = Rose Pine`. A split form `theme = light:Name,dark:Name` exists
  for desktop light/dark — this is Ghostty's analogue of Zed's object form, so
  treat it the same way: **warn and refuse to overwrite unless `--force`**, since
  it conflicts with per-block control.
- **Reload:** **not automatic** — Ghostty does not watch the file. A reload is
  triggered by the `reload_config` keybind (`ctrl+shift+,` Linux /
  `cmd+shift+,` macOS) or by sending **`SIGUSR2`** to the process.
- **Platforms:** macOS + Linux only (no Windows).

### What Ghostty needs that Zed didn't

1. **A `key = value` line patcher** (a new `adapters/_kv_patch.py`, or inline in
   the adapter): find the top-level `theme` line, replace only its value, keep
   comments/order, insert if absent, temp-file + atomic rename. Values are bare,
   not JSON-quoted.
2. **A post-write reload hook.** Because Ghostty doesn't live-reload, writing the
   file isn't enough for a *running* instance — the adapter must nudge it with
   `SIGUSR2` (best-effort: find running `ghostty` PIDs; if none, the theme loads
   on next launch). This is the **first adapter that acts beyond writing a file**,
   so the `EditorAdapter` contract grows an optional reload step (either
   `set_theme` performs it, or the apply loop calls a separate `reload()` after a
   successful write). Auto-reloading targets (Zed, WezTerm, …) leave it a no-op.
3. **macOS dual-path resolution.** On macOS, prefer the Application Support file
   when it exists (it's the one Ghostty loads); fall back to
   `~/.config/ghostty/config`. Patching the non-authoritative file silently does
   nothing, so `detect()` should report which file wins.

None of this touches `scheduler.py`, `config.py`, or `state.py` — it's contained
in the adapter plus the small reload-hook addition to the interface.

---

## Tech stack

- **Language:** Python 3.11+ (stdlib `tomllib` for reading Chronochrome's own
  config — separate from `tomlkit`, which is only needed if/when a TOML
  *target-editor* adapter is added)
- **Platforms:** macOS + Linux only for v1 (Windows explicitly deferred)
- **Packaging:** `pyproject.toml`, console_scripts entry point `chronochrome`,
  installable via `pipx` or `uv tool install`

---

## Directory layout

```
chronochrome/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── config.example.toml
├── src/
│   └── chronochrome/
│       ├── __init__.py
│       ├── cli.py              # argparse entrypoint: install/uninstall/status/apply/validate/adapters
│       ├── config.py           # load + validate TOML config, TimeBlock dataclass (editor-agnostic)
│       ├── scheduler.py        # "which block is active right now", handles midnight wraparound
│       ├── state.py            # tracks last-applied theme PER ADAPTER to avoid redundant writes
│       ├── adapters/
│       │   ├── base.py         # EditorAdapter protocol (incl. optional reload hook)
│       │   ├── _jsonc_patch.py # shared regex-based patch helper for JSONC-format editors
│       │   ├── _kv_patch.py    # `key = value` line patcher for Ghostty's config format
│       │   ├── zed.py          # v1's first concrete adapter
│       │   └── ghostty.py      # terminal adapter — key=value patch + SIGUSR2 reload
│       └── service/
│           ├── launchd.py      # generate/install/uninstall the .plist (macOS)
│           └── systemd.py      # generate/install/uninstall the .service + .timer (Linux)
├── tests/
│   ├── test_scheduler.py
│   ├── test_adapters_zed.py
│   ├── test_adapters_ghostty.py
│   ├── test_kv_patch.py
│   └── fixtures/
│       ├── sample_zed_settings.json
│       └── sample_ghostty_config
```

---

## Config schema

Lives at `~/.config/chronochrome/config.toml`. Theme names are mapped
**explicitly per editor** — there is no shared theme namespace across
editors, so a block declares a theme per adapter it wants to drive. An editor
with no entry for a block is simply left alone during that block.

```toml
# How often the OS scheduler invokes `chronochrome apply`
check_interval_minutes = 5

[[blocks]]
name = "morning"
start = "06:00"
end = "11:00"

[blocks.themes]
zed = "One Light"

[[blocks]]
name = "afternoon"
start = "11:00"
end = "17:00"

[blocks.themes]
zed = "Solarized Light"

[[blocks]]
name = "evening"
start = "17:00"
end = "21:00"

[blocks.themes]
zed = "One Dark"

[[blocks]]
name = "night"
start = "21:00"
end = "06:00"          # wraps past midnight — see scheduler.py

[blocks.themes]
zed = "Ayu Dark"
```

Validation rules (`chronochrome validate`):
- `start`/`end` must be `HH:MM`, 24-hour format
- block names must be unique
- blocks should not overlap
- warn (don't error) if blocks don't cover the full 24h — gaps just mean
  Chronochrome leaves the theme untouched during that window
- warn if a *detected* adapter has zero blocks with a theme mapped for it
  (likely a forgotten mapping, not intentional)

---

## Adapter patch strategy — read carefully (applies to `adapters/zed.py`)

- **Path:** `~/.config/zed/settings.json` (same on macOS and Linux)
- **Format:** JSONC — JSON with `//` comments and trailing commas allowed.
  **Do not** `json.load()` / `json.dump()` this file. That round-trip
  silently strips comments and reformats the entire file, destroying
  whatever the user had.
- **Strategy:** treat the file as text. Use the shared
  `adapters/_jsonc_patch.py` helper to locate the top-level `"theme"` key and
  replace only its value — everything else (comments, formatting, key order)
  stays untouched.
  - Zed accepts two forms for `"theme"`:
    - a plain string: `"theme": "One Dark"`
    - an object for system light/dark switching:
      `"theme": { "mode": "system", "light": "...", "dark": "..." }`
  - Chronochrome only ever *writes* the plain string form. If it finds the
    object form already present, that means the user has opted into
    system-appearance-based switching, which conflicts with per-block
    control — warn and refuse to overwrite unless `--force` is passed.
  - If no `"theme"` key exists, insert one near the top of the top-level
    object.
  - Write via a temp file + atomic rename, never an in-place partial write —
    Zed reloads this file live on change, so a half-written file is visible
    to Zed for a moment otherwise.

Any future JSONC-format adapter (VSCode, Sublime) should reuse
`_jsonc_patch.py` rather than reimplementing this — only the key name and
file path differ.

---

## Scheduling logic (`scheduler.py`)

- Parse `HH:MM` as minutes-since-midnight.
- A block is active if `start <= now < end`, EXCEPT when `end < start`
  (the block crosses midnight, e.g. `21:00`–`06:00`), in which case active
  means `now >= start OR now < end`.
- If zero or multiple blocks match (a config error), log a warning and leave
  all editors' themes untouched rather than guessing.
- This module has no knowledge of adapters at all — it only returns "which
  block is active," never touches a file.

---

## State tracking (`state.py`)

- Last-applied block name + theme is stored **per adapter**, at
  `~/.local/state/chronochrome/state.json`:
  ```json
  { "zed": { "block": "night", "theme": "Ayu Dark" } }
  ```
- On each invocation, only patch a given editor's file if the resolved theme
  for that editor differs from its last-applied theme — avoids spurious
  writes/file-watch churn every 5 minutes when nothing has changed, and keeps
  editors independent of each other (one editor's state never affects
  another's write decision).

---

## CLI surface

| Command | Behavior |
|---|---|
| `chronochrome install` | Writes `config.example.toml` → `~/.config/chronochrome/config.toml` if absent; installs + enables the launchd agent / systemd timer |
| `chronochrome uninstall` | Removes the scheduled job; leaves config/state files in place |
| `chronochrome apply` | One-shot: resolve current block, patch each detected adapter's file if needed. This is what the scheduler actually invokes. |
| `chronochrome status` | Show current block, active theme per adapter, next transition time, whether the scheduled job is registered |
| `chronochrome validate` | Lint the config file (overlaps, gaps, bad time format, adapters with no theme mappings) |
| `chronochrome adapters` | List registered adapters and whether each is detected on this machine |

---

## Non-goals

- Not a WASM/native extension for any editor; not published through any
  editor's official extension registry
- No Windows support in v1
- v1 ships only the Zed adapter — the interface is designed for
  extensibility, but a second adapter is not being built until Zed is solid
  and a specific editor is chosen
- Never touches any config key other than the one theme key each adapter
  owns

---

## Open questions / TODO

- [ ] Confirm exact `.plist` / systemd unit templates against the current OS versions Ricardo runs
- [ ] Decide error/notification UX for an invalid config (stderr log vs. OS notification vs. silent no-op)
- [x] Distribution: `pipx`/`uv` from GitHub now; Homebrew tooling in place —
      formula, tag-triggered release, and automatic tap bump (see `RELEASING.md`
      and `packaging/homebrew/`). Publishing the tap repo is a one-time manual step.
- [x] `--dry-run` flag for `apply` — implemented.
- [x] Second adapter **built: Ghostty** (terminal) — `adapters/ghostty.py` with
      the `key = value` patcher (`adapters/_kv_patch.py`), macOS dual-path
      resolution, split-form (`theme = light:…,dark:…`) refusal, and a
      `SIGUSR2` reload hook. VSCode is the likely third (JSONC, reuses
      `_jsonc_patch.py`).
- [x] Revisited `EditorAdapter`'s contract — added an optional **post-write
      `reload()` hook**. The apply loop calls it after a successful write;
      Ghostty signals `SIGUSR2`, auto-reloading targets (Zed) return `None`. A
      non-declarative editor like Neovim would still push on `set_theme` further.

---

## Dev workflow

- `uv sync` (or `pip install -e ".[dev]"`) to set up
- `pytest` for tests — `test_adapters_zed.py` should assert that patching
  preserves comments/formatting on a fixture file with comments in it
- `chronochrome validate` and `chronochrome apply --dry-run` are the fastest
  manual sanity checks while developing
