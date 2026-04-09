"""Tests for leading @profile mention parsing."""

from gateway.profile_mention import (
    parse_leading_profile_mention,
    strip_slack_leading_mentions_for_profile_parse,
)


def test_parse_leading_profile_basic():
    rest, slug = parse_leading_profile_mention("@security-director hello")
    assert slug == "security-director"
    assert rest == "hello"


def test_parse_leading_profile_case_insensitive_slug():
    _, slug = parse_leading_profile_mention("@Security-Director hi")
    assert slug == "security-director"


def test_parse_reserved_at_prefixes_ignored():
    t = "@file:foo bar"
    rest, slug = parse_leading_profile_mention(t)
    assert slug is None
    assert rest == t


def test_parse_reserved_slugs():
    rest, slug = parse_leading_profile_mention("@file only")
    assert slug is None
    assert rest == "@file only"


def test_parse_no_leading_at():
    t = "hello @security-director"
    rest, slug = parse_leading_profile_mention(t)
    assert slug is None
    assert rest == t


def test_parse_whitespace_before_at():
    rest, slug = parse_leading_profile_mention("  @coder run")
    assert slug == "coder"
    assert rest == "run"


def test_parse_slug_only():
    rest, slug = parse_leading_profile_mention("@coder")
    assert slug == "coder"
    assert rest == ""


def test_slack_strip_then_profile():
    raw = "<@U01ABC|alice> @security-director check this"
    stripped = strip_slack_leading_mentions_for_profile_parse(raw)
    rest, slug = parse_leading_profile_mention(stripped)
    assert slug == "security-director"
    assert rest == "check this"


def test_slack_strip_bot_style_display_name():
    raw = "<@U02BOT|hermes> @coder ping"
    stripped = strip_slack_leading_mentions_for_profile_parse(raw)
    rest, slug = parse_leading_profile_mention(stripped)
    assert slug == "coder"
    assert rest == "ping"


def test_slack_strip_broadcast_then_profile():
    raw = "<!here> @coder hello"
    stripped = strip_slack_leading_mentions_for_profile_parse(raw)
    rest, slug = parse_leading_profile_mention(stripped)
    assert slug == "coder"
    assert rest == "hello"
