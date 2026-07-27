import signal
from pathlib import Path

import pytest

from chronochrome.adapters import ghostty as ghostty_mod
from chronochrome.adapters.base import AdapterError
from chronochrome.adapters.ghostty import GhosttyAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ghostty_config"


def make_adapter(tmp_path, contents=None):
    config = tmp_path / "config"
    if contents is None:
        contents = FIXTURE.read_text(encoding="utf-8")
    if contents is not False:
        config.write_text(contents, encoding="utf-8")
    return GhosttyAdapter(settings_path=config), config


# -- read/write ------------------------------------------------------------- #
def test_reads_current_theme(tmp_path):
    adapter, _ = make_adapter(tmp_path)
    assert adapter.get_current_theme() == "Rose Pine"


def test_set_theme_preserves_comments_and_formatting(tmp_path):
    adapter, config = make_adapter(tmp_path)
    adapter.set_theme("Nord")
    result = config.read_text(encoding="utf-8")

    assert "theme = Nord\n" in result
    assert "Rose Pine" not in result
    # Comments and every other directive survive untouched.
    assert "# Ghostty configuration" in result
    assert "font-family = JetBrains Mono" in result
    assert "background-opacity = 0.95" in result
    assert "# theme = Catppuccin Mocha" in result  # commented alt untouched
    assert "keybind = ctrl+shift+r=reload_config" in result

    # Only the theme line differs from the original.
    original = FIXTURE.read_text(encoding="utf-8").splitlines()
    patched = result.splitlines()
    assert len(original) == len(patched)
    diffs = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert len(diffs) == 1
    assert "theme" in patched[diffs[0]]


def test_set_theme_is_idempotent(tmp_path):
    adapter, config = make_adapter(tmp_path)
    adapter.set_theme("Nord")
    once = config.read_text(encoding="utf-8")
    adapter.set_theme("Nord")  # no-op — value already matches
    assert config.read_text(encoding="utf-8") == once


def test_inserts_theme_when_absent(tmp_path):
    contents = "# no theme here yet\nfont-size = 13\n"
    adapter, config = make_adapter(tmp_path, contents)
    adapter.set_theme("Gruvbox Dark")
    result = config.read_text(encoding="utf-8")
    assert "theme = Gruvbox Dark\n" in result
    assert "# no theme here yet" in result
    assert "font-size = 13" in result
    assert adapter.get_current_theme() == "Gruvbox Dark"


def test_creates_file_when_missing(tmp_path):
    adapter, config = make_adapter(tmp_path, contents=False)
    assert not config.exists()
    adapter.set_theme("Solarized Light")
    assert config.exists()
    assert adapter.get_current_theme() == "Solarized Light"


def test_theme_value_with_spaces(tmp_path):
    adapter, _ = make_adapter(tmp_path)
    adapter.set_theme("Tokyo Night Storm")
    assert adapter.get_current_theme() == "Tokyo Night Storm"


def test_theme_with_newline_rejected(tmp_path):
    adapter, config = make_adapter(tmp_path)
    with pytest.raises(AdapterError):
        adapter.set_theme("Nord\nkeybind = ctrl+q=quit")
    # File untouched.
    assert adapter.get_current_theme() == "Rose Pine"


# -- split (light/dark) form ------------------------------------------------ #
def test_split_form_reported_as_no_single_theme(tmp_path):
    adapter, _ = make_adapter(tmp_path, "theme = light:Rose Pine Dawn,dark:Rose Pine\n")
    assert adapter.get_current_theme() is None


def test_split_form_refused_without_force(tmp_path):
    contents = "theme = light:Rose Pine Dawn,dark:Rose Pine\nfont-size = 13\n"
    adapter, config = make_adapter(tmp_path, contents)
    with pytest.raises(AdapterError):
        adapter.set_theme("Nord")
    assert config.read_text(encoding="utf-8") == contents  # untouched


def test_split_form_overwritten_with_force(tmp_path):
    contents = "theme = light:Rose Pine Dawn,dark:Rose Pine\nfont-size = 13\n"
    adapter, config = make_adapter(tmp_path, contents)
    adapter.set_theme("Nord", force=True)
    result = config.read_text(encoding="utf-8")
    assert "theme = Nord\n" in result
    assert "light:" not in result
    assert "font-size = 13" in result  # sibling preserved


# -- detection & path resolution ------------------------------------------- #
def test_detect(tmp_path):
    adapter, _ = make_adapter(tmp_path)
    assert adapter.detect() is True
    missing = GhosttyAdapter(settings_path=tmp_path / "nope" / "config")
    assert missing.detect() is False


def test_macos_prefers_app_support_when_present(tmp_path):
    app_support = tmp_path / "app_support_config"
    xdg = tmp_path / "xdg_config"
    app_support.write_text("theme = AppSupport\n", encoding="utf-8")
    xdg.write_text("theme = Xdg\n", encoding="utf-8")
    adapter = GhosttyAdapter(candidates=[app_support, xdg])
    assert adapter.settings_path() == app_support
    assert adapter.get_current_theme() == "AppSupport"


def test_macos_falls_back_to_xdg_when_app_support_absent(tmp_path):
    app_support = tmp_path / "app_support_config"  # does not exist
    xdg = tmp_path / "xdg_config"
    xdg.write_text("theme = Xdg\n", encoding="utf-8")
    adapter = GhosttyAdapter(candidates=[app_support, xdg])
    assert adapter.settings_path() == xdg
    assert adapter.get_current_theme() == "Xdg"


def test_creation_target_is_most_preferred_when_none_exist(tmp_path):
    app_support = tmp_path / "app_support_config"
    xdg = tmp_path / "xdg_config"
    adapter = GhosttyAdapter(candidates=[app_support, xdg])
    assert adapter.settings_path() == app_support  # neither exists → first


def test_default_candidates_by_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    linux = GhosttyAdapter(platform="linux")._candidates()
    assert linux == [tmp_path / ".config" / "ghostty" / "config"]

    mac = GhosttyAdapter(platform="darwin")._candidates()
    assert mac[0] == (
        tmp_path
        / "Library"
        / "Application Support"
        / "com.mitchellh.ghostty"
        / "config"
    )
    assert mac[1] == tmp_path / ".config" / "ghostty" / "config"


def test_xdg_config_home_respected(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdgroot"))
    candidates = GhosttyAdapter(platform="linux")._candidates()
    assert candidates == [tmp_path / "xdgroot" / "ghostty" / "config"]


# -- reload hook ------------------------------------------------------------ #
def test_reload_signals_running_processes(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)
    monkeypatch.setattr(adapter, "_running_pids", lambda: [111, 222])

    sent = []
    monkeypatch.setattr(ghostty_mod.os, "kill", lambda pid, sig: sent.append((pid, sig)))

    note = adapter.reload()
    assert sent == [(111, signal.SIGUSR2), (222, signal.SIGUSR2)]
    assert note is not None
    assert "2" in note


def test_reload_noop_when_not_running(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)
    monkeypatch.setattr(adapter, "_running_pids", lambda: [])
    assert adapter.reload() is None


def test_reload_is_best_effort_on_kill_error(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)
    monkeypatch.setattr(adapter, "_running_pids", lambda: [111, 222])

    def boom(pid, sig):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(ghostty_mod.os, "kill", boom)
    # Every signal fails → nothing reported, and no exception escapes.
    assert adapter.reload() is None


def test_reload_singular_wording(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)
    monkeypatch.setattr(adapter, "_running_pids", lambda: [111])
    monkeypatch.setattr(ghostty_mod.os, "kill", lambda pid, sig: None)
    note = adapter.reload()
    assert "1 running Ghostty process " in note


def test_running_pids_parses_pgrep(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)

    class FakeProc:
        returncode = 0
        stdout = "111\n222\n"

    monkeypatch.setattr(ghostty_mod.subprocess, "run", lambda *a, **k: FakeProc())
    assert adapter._running_pids() == [111, 222]


def test_running_pids_empty_on_no_match(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)

    class FakeProc:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(ghostty_mod.subprocess, "run", lambda *a, **k: FakeProc())
    assert adapter._running_pids() == []


def test_running_pids_empty_when_pgrep_missing(tmp_path, monkeypatch):
    adapter, _ = make_adapter(tmp_path)

    def boom(*a, **k):
        raise FileNotFoundError("no pgrep")

    monkeypatch.setattr(ghostty_mod.subprocess, "run", boom)
    assert adapter._running_pids() == []
