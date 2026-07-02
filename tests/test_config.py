import textwrap

import pytest

from chronochrome.config import (
    ConfigError,
    load_config,
    parse_hhmm,
    validate_config,
)


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


VALID = """
    check_interval_minutes = 5

    [[blocks]]
    name = "day"
    start = "06:00"
    end = "21:00"
    [blocks.themes]
    zed = "One Light"

    [[blocks]]
    name = "night"
    start = "21:00"
    end = "06:00"
    [blocks.themes]
    zed = "Ayu Dark"
"""


def test_parse_hhmm():
    assert parse_hhmm("00:00") == 0
    assert parse_hhmm("06:30") == 390
    assert parse_hhmm("23:59") == 1439


@pytest.mark.parametrize("bad", ["6:00", "24:00", "12:60", "noon", "12-00", "1200"])
def test_parse_hhmm_rejects_bad(bad):
    with pytest.raises(ConfigError):
        parse_hhmm(bad)


def test_load_valid_config(tmp_path):
    config = load_config(write_config(tmp_path, VALID))
    assert config.check_interval_minutes == 5
    assert [b.name for b in config.blocks] == ["day", "night"]
    assert config.blocks[0].theme_for("zed") == "One Light"
    assert config.blocks[1].wraps_midnight


def test_missing_file_errors():
    with pytest.raises(ConfigError):
        load_config("/no/such/config.toml")


def test_validate_full_coverage_is_clean(tmp_path):
    result = validate_config(write_config(tmp_path, VALID))
    assert result.ok
    assert result.errors == []


def test_validate_detects_overlap(tmp_path):
    body = """
        [[blocks]]
        name = "a"
        start = "09:00"
        end = "12:00"
        [blocks.themes]
        zed = "One Light"

        [[blocks]]
        name = "b"
        start = "11:00"
        end = "14:00"
        [blocks.themes]
        zed = "One Dark"
    """
    result = validate_config(write_config(tmp_path, body))
    assert not result.ok
    assert any("overlap" in e for e in result.errors)


def test_validate_warns_on_gap(tmp_path):
    body = """
        [[blocks]]
        name = "morning"
        start = "06:00"
        end = "11:00"
        [blocks.themes]
        zed = "One Light"
    """
    result = validate_config(write_config(tmp_path, body))
    # A gap is a warning, not an error.
    assert result.ok
    assert any("uncovered" in w for w in result.warnings)


def test_validate_duplicate_names_error(tmp_path):
    body = """
        [[blocks]]
        name = "dup"
        start = "06:00"
        end = "12:00"

        [[blocks]]
        name = "dup"
        start = "12:00"
        end = "06:00"
    """
    result = validate_config(write_config(tmp_path, body))
    assert any("duplicate" in e for e in result.errors)


def test_validate_warns_unmapped_detected_adapter(tmp_path):
    body = """
        [[blocks]]
        name = "allday"
        start = "00:00"
        end = "23:59"
        [blocks.themes]
        vscode = "Some Theme"
    """
    result = validate_config(
        write_config(tmp_path, body), detected_adapters=["zed"]
    )
    assert any("zed" in w for w in result.warnings)
