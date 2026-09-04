from pathlib import Path

from kuroshio.core.ips import IPS, parse_ips, validate
from kuroshio.core.ips.schema import VERDICT_ORDER, verdict_at_least

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_conservative_example_parses_and_validates():
    ips = parse_ips(EXAMPLES / "ips-conservative.md")
    assert ips.caps.max_adverse_excursion_pct == -10
    assert ips.caps.book_vol_target_pct is None  # opt-in: every example leaves it unset
    assert ips.risk_profile == "conservative"
    assert ips.caps.position_pct == 5
    assert ips.caps.position_hard_pct == 15
    assert ips.caps.theme_pct == 15
    assert ips.turnover.hurdle == 0.25
    assert ips.turnover.verdict_floor == "overweight"
    assert ips.turnover.max_swaps_per_week == 1
    assert ips.philosophy  # body captured
    assert validate(ips) == []


def test_balanced_example_parses_and_validates():
    ips = parse_ips(EXAMPLES / "ips-balanced.md")
    assert ips.caps.max_adverse_excursion_pct == -15
    assert ips.caps.book_vol_target_pct is None  # opt-in: every example leaves it unset
    assert ips.caps.position_pct == 10
    assert ips.caps.position_hard_pct == 25
    assert ips.caps.theme_pct == 20
    assert ips.turnover.hurdle == 0.15
    assert ips.turnover.verdict_floor == "neutral"
    assert ips.turnover.max_swaps_per_week == 2
    assert validate(ips) == []


def test_aggressive_example_parses_and_validates():
    ips = parse_ips(EXAMPLES / "ips-aggressive.md")
    assert ips.caps.max_adverse_excursion_pct == -20
    assert ips.caps.book_vol_target_pct is None  # aggressive rides the vol, unset
    assert ips.caps.position_pct == 15
    assert ips.caps.position_hard_pct == 25
    assert ips.caps.theme_pct == 30
    assert ips.turnover.hurdle == 0.10
    assert ips.turnover.verdict_floor == "neutral"
    assert ips.turnover.max_swaps_per_week == 4
    assert validate(ips) == []


def test_no_frontmatter_gives_defaults_and_whole_text_as_philosophy():
    text = "Just some philosophy, no YAML frontmatter here.\nSecond line."
    ips = parse_ips(text)
    assert ips == IPS(philosophy=text.strip())
    assert ips.version == 1
    assert ips.caps.position_pct == 10  # default
    assert validate(ips) == []


def test_unknown_top_level_keys_land_in_extra():
    text = """---
version: 1
risk_profile: balanced
totally_new_field: 42
another_one: {nested: true}
---
Philosophy body.
"""
    ips = parse_ips(text)
    assert ips.extra == {"totally_new_field": 42, "another_one": {"nested": True}}
    assert validate(ips) == []


def test_validate_catches_bad_version():
    ips = IPS(version=2)
    problems = validate(ips)
    assert any("version" in p for p in problems)


def test_validate_catches_position_pct_over_hard_cap():
    ips = IPS()
    ips.caps.position_pct = 30
    ips.caps.position_hard_pct = 25
    problems = validate(ips)
    assert any("position_pct" in p for p in problems)


def test_validate_catches_unknown_verdict_floor():
    ips = IPS()
    ips.turnover.verdict_floor = "bullish"
    problems = validate(ips)
    assert any("verdict_floor" in p for p in problems)


def test_validate_catches_bad_exemption_cap_name():
    from kuroshio.core.ips.schema import CapExemption

    ips = IPS()
    ips.caps.exemptions = [CapExemption(ticker="1234", cap="not_a_real_cap", reason="test")]
    problems = validate(ips)
    assert any("not_a_real_cap" in p for p in problems)


def test_verdict_at_least_ordering():
    assert verdict_at_least("buy", "neutral") is True
    assert verdict_at_least("overweight", "neutral") is True
    assert verdict_at_least("neutral", "neutral") is True
    assert verdict_at_least("underweight", "neutral") is False
    assert verdict_at_least("sell", "neutral") is False
    assert verdict_at_least("bogus", "neutral") is False
    assert verdict_at_least("buy", "bogus") is False


def test_verdict_hold_is_alias_for_neutral():
    # LLM agents emit "Hold" (PortfolioRating), not "neutral".
    assert verdict_at_least("Hold", "neutral") is True
    assert verdict_at_least("hold", "underweight") is True
    assert verdict_at_least("hold", "overweight") is False
    assert verdict_at_least("buy", "Hold") is True
    assert verdict_at_least("sell", "hold") is False
    assert VERDICT_ORDER == ["sell", "underweight", "neutral", "overweight", "buy"]  # no sixth rung


def test_validate_catches_bad_friction():
    # The allocator adds friction/100 to the turnover hurdle, so a friction value that
    # is the wrong type blows that arithmetic up (None / 100 -> TypeError) and one that
    # is the wrong *magnitude* silently corrupts the gate: nan makes `gap < hurdle` False
    # for every gap (every challenger becomes a SWAP), inf makes it True for every gap
    # (every swap vanishes), and a negative lowers the bar below the user's own hurdle.
    # cli.cmd_propose bails on any validate() problem before calling propose(), so
    # catching them here keeps "ips-validate said OK" and "propose behaves" one answer.
    malformed = (
        "tw_roundtrip_pct:", "us_roundtrip_pct:",  # present but null
        'tw_roundtrip_pct: "0.585"', "us_roundtrip_pct: abc",  # non-numeric
        "tw_roundtrip_pct: .nan", "us_roundtrip_pct: .inf",  # non-finite
        "tw_roundtrip_pct: -10.0", "us_roundtrip_pct: 100.0",  # outside [0, 100)
    )
    for friction in malformed:
        ips = parse_ips(f"---\nfriction:\n  {friction}\n---\nbody\n")
        problems = validate(ips)
        assert any("friction" in p for p in problems), f"{friction!r} was accepted"


def test_mae_threshold_parses_and_defaults():
    assert IPS().caps.max_adverse_excursion_pct == -15
    ips = parse_ips("---\ncaps:\n  max_adverse_excursion_pct: -22.5\n---\nbody\n")
    assert ips.caps.max_adverse_excursion_pct == -22.5
    assert validate(ips) == []
    # it lives under caps but is not an exemptible one: a per-ticker carve-out from
    # "no silent holding of losers" is the thing this card exists to refuse.
    problems = validate(parse_ips(
        "---\ncaps:\n  exemptions:\n    - {ticker: A, cap: max_adverse_excursion_pct}\n---\nbody\n"
    ))
    assert any("unknown cap field" in p for p in problems)


def test_validate_catches_a_mae_threshold_with_the_wrong_sign_or_type():
    """The sign carries the meaning — it is a loss from entry, so it is negative, and a
    user who writes the percent unsigned must be told which is expected rather than
    handed a threshold that fires on every position (>= 0) or on none (<= -100).
    Type failures and range failures say different things (see T18 for why)."""
    wrong_sign = ("caps:\n  max_adverse_excursion_pct: 15", "caps:\n  max_adverse_excursion_pct: 0")
    for frontmatter in wrong_sign:
        problems = validate(parse_ips(f"---\n{frontmatter}\n---\nbody\n"))
        assert any(
            "max_adverse_excursion_pct" in p and "negative percent" in p for p in problems
        ), frontmatter

    for frontmatter in ("max_adverse_excursion_pct: -100", "max_adverse_excursion_pct: -100.1"):
        problems = validate(parse_ips(f"---\ncaps:\n  {frontmatter}\n---\nbody\n"))
        assert any("negative percent" in p for p in problems), frontmatter

    for frontmatter in ("max_adverse_excursion_pct:", 'max_adverse_excursion_pct: "-15"',
                        "max_adverse_excursion_pct: abc", "max_adverse_excursion_pct: .nan"):
        problems = validate(parse_ips(f"---\ncaps:\n  {frontmatter}\n---\nbody\n"))
        assert any("max_adverse_excursion_pct" in p for p in problems), frontmatter
    typed = validate(parse_ips('---\ncaps:\n  max_adverse_excursion_pct: "-15"\n---\nbody\n'))
    ranged = validate(parse_ips("---\ncaps:\n  max_adverse_excursion_pct: 15\n---\nbody\n"))
    assert typed != ranged  # the string case is not reported with a rule its value meets


def test_book_vol_target_pct_parses_and_defaults_to_off():
    assert IPS().caps.book_vol_target_pct is None
    ips = parse_ips("---\ncaps:\n  book_vol_target_pct: 15\n---\nbody\n")
    assert ips.caps.book_vol_target_pct == 15
    assert validate(ips) == []


def test_validate_catches_a_book_vol_target_out_of_range():
    for bad in ("book_vol_target_pct: 0", "book_vol_target_pct: 150"):
        problems = validate(parse_ips(f"---\ncaps:\n  {bad}\n---\nbody\n"))
        assert any("book_vol_target_pct" in p for p in problems), bad


def test_book_vol_target_pct_is_not_exemptable():
    # book-level, like max_adverse_excursion_pct — a per-ticker exemption from a number
    # that describes the whole book, not one position, is meaningless.
    problems = validate(parse_ips(
        "---\ncaps:\n  exemptions:\n    - {ticker: A, cap: book_vol_target_pct}\n---\nbody\n"
    ))
    assert any("unknown cap field" in p for p in problems)

def test_risk_budget_pct_parses_and_is_validated():
    text = """---
version: 1
caps:
  risk_budget_pct: 0.5
---
Philosophy body.
"""
    ips = parse_ips(text)
    assert ips.caps.risk_budget_pct == 0.5
    assert validate(ips) == []

    # 0% of NAV risked sizes every position at nothing; a non-number crashes the
    # allocator's division rather than being rejected here.
    for bad in (0, "1"):
        ips.caps.risk_budget_pct = bad
        assert any("risk_budget_pct" in p for p in validate(ips))
