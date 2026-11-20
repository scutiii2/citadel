"""Text rules for a shared fragment: cut a section out of a Markdown file, and keep private links out of a snapshot.

shortcut: only Markdown links, images and [[wiki links]] are rewritten; an HTML `<a href>` or a bare path in the text
stays. Upgrade if shared text ever needs a stricter filter.
"""

from __future__ import annotations

import re

_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]*)\)")
_WIKI = re.compile(r"!?\[\[([^\]\n]*)\]\]")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_PUBLIC = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


def drop_private_links(text: str) -> str:
    def link(match: re.Match[str]) -> str:
        image, label, target = match.group(1), match.group(2), match.group(3).strip()
        return match.group(0) if not image and _PUBLIC.match(target) else label

    def wiki(match: re.Match[str]) -> str:
        inner = match.group(1)
        return (inner.split("|", 1)[1] if "|" in inner else inner.split("#", 1)[0]).strip()

    return _WIKI.sub(wiki, _LINK.sub(link, text))


def extract_section(body: str, heading: str) -> str | None:
    """The heading line and everything under it up to the next heading of the same or a higher level; None if absent."""
    wanted = " ".join(heading.split()).lower()
    lines = body.split("\n")
    fenced = False
    start = level = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        found = _HEADING.match(line)
        if not found:
            continue
        depth = len(found.group(1))
        if start is None:
            if " ".join(found.group(2).split()).lower() == wanted:
                start, level = index, depth
        elif depth <= level:
            return "\n".join(lines[start:index]).strip()
    return "\n".join(lines[start:]).strip() if start is not None else None
