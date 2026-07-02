from chronochrome.config import TimeBlock
from chronochrome.scheduler import (
    is_active,
    minutes_until,
    next_transition,
    resolve_active_block,
)


def block(name, start, end, **themes):
    return TimeBlock(name=name, start=start, end=end, themes=themes)


def hm(h, m=0):
    return h * 60 + m


MORNING = block("morning", hm(6), hm(11), zed="One Light")
AFTERNOON = block("afternoon", hm(11), hm(17), zed="Solarized Light")
EVENING = block("evening", hm(17), hm(21), zed="One Dark")
NIGHT = block("night", hm(21), hm(6), zed="Ayu Dark")  # wraps midnight
ALL = [MORNING, AFTERNOON, EVENING, NIGHT]


def test_normal_block_active_window():
    assert is_active(MORNING, hm(6))
    assert is_active(MORNING, hm(10, 59))
    assert not is_active(MORNING, hm(11))  # end is exclusive
    assert not is_active(MORNING, hm(5, 59))


def test_wraparound_block():
    assert NIGHT.wraps_midnight
    assert is_active(NIGHT, hm(21))
    assert is_active(NIGHT, hm(23, 59))
    assert is_active(NIGHT, hm(0))
    assert is_active(NIGHT, hm(5, 59))
    assert not is_active(NIGHT, hm(6))
    assert not is_active(NIGHT, hm(12))


def test_resolve_single_match_across_the_day():
    assert resolve_active_block(ALL, hm(8)).block is MORNING
    assert resolve_active_block(ALL, hm(13)).block is AFTERNOON
    assert resolve_active_block(ALL, hm(19)).block is EVENING
    assert resolve_active_block(ALL, hm(22)).block is NIGHT
    assert resolve_active_block(ALL, hm(3)).block is NIGHT  # after midnight


def test_resolve_no_match_is_reported_not_guessed():
    gapped = [MORNING, EVENING]  # 11:00–17:00 and nights uncovered
    res = resolve_active_block(gapped, hm(13))
    assert res.block is None
    assert res.reason == "no-match"


def test_resolve_multiple_match_is_reported():
    overlap = [block("a", hm(9), hm(12)), block("b", hm(10), hm(13))]
    res = resolve_active_block(overlap, hm(11))
    assert res.block is None
    assert res.reason == "multiple-match"


def test_next_transition_and_countdown():
    # At 08:00 the next boundary is 11:00 (afternoon start / morning end).
    nxt = next_transition(ALL, hm(8))
    assert nxt == hm(11)
    assert minutes_until(nxt, hm(8)) == 180


def test_next_transition_wraps_past_midnight():
    # At 22:00 the next boundary is 06:00 tomorrow (night end / morning start).
    nxt = next_transition(ALL, hm(22))
    assert nxt == hm(6)
    assert minutes_until(nxt, hm(22)) == 8 * 60
