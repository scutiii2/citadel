"""Text rules for a shared fragment: cut a section out of a Markdown file, and keep private links out of a snapshot.

shortcut: only Markdown links, images and [[wiki links]] are rewritten; an HTML `<a href>` or a bare path in the text
stays. Upgrade if shared text ever needs a stricter filter.
"""

from __future__ import annotations

import re

_LABEL = re.compile(r"(!?)\[((?:\\.|[^\[\]\\\r\n]|\[(?:\\.|[^\[\]\\\r\n])*\])*)\]")
_DEFINITION = re.compile(r"^ {0,3}\[([^\]\r\n]+)\]:[ \t]*(?:\r?\n[ \t]*)?(\S[^\r\n]*)(?:\r?\n|$)", re.MULTILINE)
_ANGLE = re.compile(r"<((?:\\.|[^\\<>\r\n])*)>")
_TITLE = re.compile(r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|\((?:\\.|[^)\\\r\n])*\))""")
_SPACE = re.compile(r"[ \t\r\n]*")
_WIKI = re.compile(r"!?\[\[([^\]\n]*)\]\]")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_CODE_FENCE = re.compile(r"(`{3,}|~{3,})(.*)")
_PUBLIC = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


def _inline_target(text: str, opening: int) -> tuple[str, int] | None:
    """Read a Markdown destination and its optional title after an opening parenthesis."""
    start = end = _SPACE.match(text, opening + 1).end()
    if text.startswith("<", start):
        angle = _ANGLE.match(text, start)
        if angle is None:
            return None
        target, end = angle.group(1), angle.end()
    else:
        depth = 0
        while end < len(text) and not (char := text[end]).isspace():
            if char == "\\" and end + 1 < len(text):
                end += 2
                continue
            if char == ")" and depth == 0:
                break
            if char == "(":
                depth += 1
                if depth > 32:
                    return None
            elif char == ")":
                depth -= 1
            end += 1
        if depth:
            return None
        target = text[start:end]

    after_space = _SPACE.match(text, end).end()
    if after_space != end and not text.startswith(")", after_space):
        title = _TITLE.match(text, after_space)
        if title is None:
            return None
        after_space = _SPACE.match(text, title.end()).end()
    return (target, after_space + 1) if text.startswith(")", after_space) else None


def _reference_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def drop_private_links(text: str) -> str:
    def wiki(match: re.Match[str]) -> str:
        inner = match.group(1)
        return (inner.split("|", 1)[1] if "|" in inner else inner.split("#", 1)[0]).strip()

    references: dict[str, bool] = {}

    def definition(match: re.Match[str]) -> str:
        label, destination = match.groups()
        parsed = _inline_target(f"({destination})", 0)
        if parsed is None or parsed[1] != len(destination) + 2:
            return match.group(0)
        public = _PUBLIC.match(parsed[0]) is not None
        references.setdefault(_reference_key(label), public)
        return match.group(0) if public else ""

    text = _DEFINITION.sub(definition, _WIKI.sub(wiki, text))
    chunks: list[str] = []
    cursor = 0
    for match in _LABEL.finditer(text):
        if match.start() < cursor:
            continue
        image, label = match.groups()
        stop = match.end()
        inline = _inline_target(text, stop) if text.startswith("(", stop) else None
        if inline is not None:
            target, stop = inline
            public = _PUBLIC.match(target) is not None
        else:
            ref = _LABEL.match(text, stop) if text.startswith("[", stop) else None
            key = _reference_key((ref.group(2) or label) if ref else label)
            if key not in references:
                continue
            public = references[key]
            if ref:
                stop = ref.end()
        chunks.append(text[cursor:match.start()])
        clean_label = drop_private_links(label) if "[" in label else label
        chunks.append(f"[{clean_label}]{text[match.end():stop]}" if public and not image else clean_label)
        cursor = stop
    chunks.append(text[cursor:])
    return "".join(chunks)


def extract_section(body: str, heading: str) -> str | None:
    """The heading line and everything under it up to the next heading of the same or a higher level; None if absent."""
    wanted = " ".join(heading.split()).lower()
    lines = body.split("\n")
    fence = ""
    start = level = None
    for index, line in enumerate(lines):
        marker = _CODE_FENCE.match(line.lstrip())
        if fence:
            if marker:
                closer, suffix = marker.groups()
                if closer[0] == fence[0] and len(closer) >= len(fence) and not suffix.strip():
                    fence = ""
            continue
        if marker:
            fence = marker.group(1)
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
