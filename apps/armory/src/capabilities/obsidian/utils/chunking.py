"""Heading-aware Markdown chunks. Size is estimated at four characters per token."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import yaml



@dataclass
class Chunk:
    path: str
    heading: tuple[str, ...]
    text: str
    tags: list[str]
    frontmatter: dict[str, Any]
    wikilinks: list[str]


def chunk_note(path: str, text: str) -> list[Chunk]:
    """Split outside code fences by heading, then into ~450-token spans.
    YAML is safe-loaded into JSON-safe metadata (dates become strings)."""
    frontmatter: dict[str, Any] = {}
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if match:
        loaded = yaml.safe_load(match[1]) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Obsidian frontmatter must be a mapping")
        frontmatter = json.loads(json.dumps(loaded, default=str))
        text = text[match.end():]
    raw_tags = frontmatter.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[,\s]+", raw_tags)
    tags = sorted({str(t).lstrip("#") for t in raw_tags if str(t)}) if isinstance(raw_tags, list) else []
    tags = sorted(set(tags) | set(re.findall(r"(?<!\w)#([\w/-]+)", text)))
    links = sorted({m.split("|", 1)[0].split("#", 1)[0].strip() for m in re.findall(r"\[\[([^\]]+)\]\]", text)} - {""})
    sections: list[tuple[tuple[str, ...], str]] = []
    trail: list[tuple[int, str]] = []
    lines: list[str] = []
    fence = ""
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if not fence and not marker else None
        if heading:
            if "".join(lines).strip():
                sections.append((tuple(t[1] for t in trail), "".join(lines)))
            lines = []
            level = len(heading[1])
            trail = [t for t in trail if t[0] < level] + [(level, heading[2])]
        lines.append(line)
    if "".join(lines).strip():
        sections.append((tuple(t[1] for t in trail), "".join(lines)))
    chunks = []
    for heading_trail, body in sections:
        while body:
            end = min(1800, len(body))
            if end < len(body):
                boundary = max(body.rfind("\n", 1200, end), body.rfind(" ", 1200, end))
                if boundary >= 1200:
                    end = boundary + 1
            part, body = body[:end], body[end:]
            if part.strip():
                chunks.append(Chunk(path, heading_trail, part, tags, frontmatter, links))
    return chunks
