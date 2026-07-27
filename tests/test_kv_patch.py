import pytest

from chronochrome.adapters import _kv_patch as kv


def test_get_value_finds_theme():
    text = "theme = Rose Pine\nfont-size = 13\n"
    assert kv.get_value(text, "theme") == "Rose Pine"


def test_get_value_absent():
    assert kv.get_value("font-size = 13\n", "theme") is None


def test_get_value_ignores_comment_lines():
    text = "# theme = Catppuccin\nfont-size = 13\n"
    assert kv.get_value(text, "theme") is None


def test_get_value_strips_surrounding_whitespace():
    assert kv.get_value("theme =   Rose Pine  \n", "theme") == "Rose Pine"


def test_get_value_handles_no_space_form():
    assert kv.get_value("theme=Nord\n", "theme") == "Nord"


def test_last_occurrence_wins():
    # Ghostty applies the last value of a repeated scalar key.
    text = "theme = One\ntheme = Two\n"
    assert kv.get_value(text, "theme") == "Two"


def test_replace_preserves_comments_and_other_lines():
    text = (
        "# banner\n"
        "theme = Rose Pine\n"
        "font-size = 13\n"
        "# theme = commented\n"
    )
    out = kv.replace_value(text, "theme", "Nord")
    assert "theme = Nord\n" in out
    assert "Rose Pine" not in out
    assert "# banner\n" in out
    assert "font-size = 13\n" in out
    assert "# theme = commented\n" in out  # comment left untouched


def test_replace_preserves_spacing_and_line_ending():
    # No spaces around '=' and a CRLF ending must both survive.
    text = "theme=Rose Pine\r\n"
    out = kv.replace_value(text, "theme", "Nord")
    assert out == "theme=Nord\r\n"


def test_replace_only_touches_theme_line():
    text = "a = 1\ntheme = Rose Pine\nb = 2\n"
    out = kv.replace_value(text, "theme", "Ayu Mirage")
    original = text.splitlines()
    patched = out.splitlines()
    assert len(original) == len(patched)
    diffs = [i for i, (x, y) in enumerate(zip(original, patched)) if x != y]
    assert diffs == [1]


def test_replace_targets_last_occurrence():
    text = "theme = One\ntheme = Two\n"
    out = kv.replace_value(text, "theme", "Three")
    assert out == "theme = One\ntheme = Three\n"


def test_replace_missing_key_raises():
    with pytest.raises(kv.KvPatchError):
        kv.replace_value("font-size = 13\n", "theme", "Nord")


def test_replace_rejects_newline_value():
    with pytest.raises(kv.KvPatchError):
        kv.replace_value("theme = Rose Pine\n", "theme", "Nord\nfoo = bar")


def test_insert_appends_directive():
    text = "font-size = 13\n"
    out = kv.insert_key(text, "theme", "Nord")
    assert out == "font-size = 13\ntheme = Nord\n"


def test_insert_into_empty_text():
    assert kv.insert_key("", "theme", "Nord") == "theme = Nord\n"


def test_insert_adds_missing_trailing_newline():
    out = kv.insert_key("font-size = 13", "theme", "Nord")
    assert out == "font-size = 13\ntheme = Nord\n"


def test_value_with_spaces_round_trips():
    out = kv.insert_key("", "theme", "Rosé Pine Moon")
    assert kv.get_value(out, "theme") == "Rosé Pine Moon"
