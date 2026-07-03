from pathlib import Path

import pytest

from chronochrome.adapters.base import AdapterError
from chronochrome.adapters.zed import ZedAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "sample_zed_settings.json"


def make_adapter(tmp_path, contents=None):
    settings = tmp_path / "settings.json"
    if contents is None:
        contents = FIXTURE.read_text(encoding="utf-8")
    if contents is not False:
        settings.write_text(contents, encoding="utf-8")
    return ZedAdapter(settings_path=settings), settings


def test_reads_current_theme(tmp_path):
    adapter, _ = make_adapter(tmp_path)
    assert adapter.get_current_theme() == "One Dark"


def test_set_theme_preserves_comments_and_formatting(tmp_path):
    adapter, settings = make_adapter(tmp_path)
    adapter.set_theme("Ayu Dark")
    result = settings.read_text(encoding="utf-8")

    # The theme value changed...
    assert '"theme": "Ayu Dark"' in result
    assert '"One Dark"' not in result
    # ...but every comment and every other key survived untouched.
    assert "// Zed settings" in result
    assert "// trailing comment on a primitive" in result
    assert "/* block comment describing the editor section */" in result
    assert '"buffer_font_size": 15,' in result
    assert '"tab_size": 4' in result
    assert '"metrics": false' in result

    # Only the theme line differs from the original.
    original = FIXTURE.read_text(encoding="utf-8").splitlines()
    patched = result.splitlines()
    assert len(original) == len(patched)
    diffs = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert len(diffs) == 1
    assert "theme" in patched[diffs[0]]


def test_set_theme_is_atomic_and_idempotent(tmp_path):
    adapter, settings = make_adapter(tmp_path)
    adapter.set_theme("Ayu Dark")
    once = settings.read_text(encoding="utf-8")
    adapter.set_theme("Ayu Dark")  # no-op — value already matches
    assert settings.read_text(encoding="utf-8") == once


def test_object_form_refused_without_force(tmp_path):
    contents = (
        "{\n"
        '  "theme": { "mode": "system", "light": "One Light", "dark": "One Dark" },\n'
        '  "vim_mode": true\n'
        "}\n"
    )
    adapter, settings = make_adapter(tmp_path, contents)
    with pytest.raises(AdapterError):
        adapter.set_theme("Ayu Dark")
    # File untouched.
    assert settings.read_text(encoding="utf-8") == contents


def test_object_form_overwritten_with_force(tmp_path):
    contents = (
        "{\n"
        '  "theme": { "mode": "system", "light": "One Light", "dark": "One Dark" },\n'
        '  "vim_mode": true\n'
        "}\n"
    )
    adapter, settings = make_adapter(tmp_path, contents)
    adapter.set_theme("Ayu Dark", force=True)
    result = settings.read_text(encoding="utf-8")
    assert '"theme": "Ayu Dark"' in result
    assert '"mode"' not in result
    assert '"vim_mode": true' in result  # sibling preserved


def test_inserts_theme_when_absent(tmp_path):
    contents = (
        "{\n"
        "  // no theme here yet\n"
        '  "vim_mode": false\n'
        "}\n"
    )
    adapter, settings = make_adapter(tmp_path, contents)
    adapter.set_theme("Gruvbox Dark")
    result = settings.read_text(encoding="utf-8")
    assert '"theme": "Gruvbox Dark"' in result
    assert "// no theme here yet" in result
    assert '"vim_mode": false' in result
    assert adapter.get_current_theme() == "Gruvbox Dark"


def test_creates_file_when_missing(tmp_path):
    adapter, settings = make_adapter(tmp_path, contents=False)
    assert not settings.exists()
    adapter.set_theme("One Light")
    assert settings.exists()
    assert adapter.get_current_theme() == "One Light"


def test_theme_value_with_special_characters(tmp_path):
    adapter, settings = make_adapter(tmp_path)
    adapter.set_theme('Ayu "Mirage"')
    # Round-trips through JSON escaping.
    assert adapter.get_current_theme() == 'Ayu "Mirage"'


def test_detect(tmp_path):
    adapter, settings = make_adapter(tmp_path)
    assert adapter.detect() is True
    missing = ZedAdapter(settings_path=tmp_path / "nope" / "settings.json")
    assert missing.detect() is False
