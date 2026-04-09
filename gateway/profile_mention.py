"""Leading ``@profile-slug`` mention for messaging gateways (Slack, etc.)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Slack wraps people/bots as ``<@U123>`` or ``<@U123|name>``; usergroups / broadcast as ``<!…>``.
_SLACK_LEADING_TOKEN = re.compile(
    r"^(?:<@[^>]+>|<![^>]+>)\s*",
    re.IGNORECASE,
)


def strip_slack_leading_mentions_for_profile_parse(text: str) -> str:
    """Remove leading Slack mention tokens so ``@profile-slug`` can appear first for parsing.

    The Slack adapter strips the *bot* mention in channels, but messages may still
    begin with another ``<@U…>`` (e.g. a human ping) before ``@security-director``.
    """
    if not text or not isinstance(text, str):
        return text
    s = text.lstrip()
    while True:
        m = _SLACK_LEADING_TOKEN.match(s)
        if not m:
            break
        s = s[m.end() :].lstrip()
    return s


# Hermes @ context refs — do not treat as profile names.
_RESERVED_AT_PREFIXES = (
    "file:",
    "folder:",
    "diff",
)
_RESERVED_SLUGS = frozenset({"file", "folder", "diff"})


def parse_leading_profile_mention(text: str) -> Tuple[str, Optional[str]]:
    """If *text* starts with ``@<profile>`` (optional whitespace), return the rest
    and the profile slug; otherwise return (*text*, None).

    Does not match Slack ``<@U123>`` bot mentions — only ASCII ``@word`` at the
    start of the message body.
    """
    if not text or not isinstance(text, str):
        return text, None
    s = text.lstrip()
    if not s.startswith("@"):
        return text, None
    low = s.lower()
    for pref in _RESERVED_AT_PREFIXES:
        if low[1:].startswith(pref):
            return text, None
    # @slug … or @slug-only (profile ids: letter/digit then [a-z0-9_-]*)
    m = re.match(r"^@([a-z0-9][a-z0-9_-]*)(?:\s+|$)", s, re.IGNORECASE)
    if not m:
        return text, None
    slug = m.group(1).lower()
    if slug in _RESERVED_SLUGS:
        return text, None
    rest = s[m.end() :].lstrip()
    return rest, slug
