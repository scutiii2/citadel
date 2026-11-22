"""Skills: learned how-tos kept in the Brain, one small Markdown file each.

<root>/accounts/<uid>/.skills/<id>.md has a header of `key: <JSON>` lines (id, title, when_to_use, tools, status,
successes, failures, created_at) and the steps as its body. The dot folder keeps skills out of the notes scan
and the notes quota; the account purge already deletes it. An agent can only propose, search and mark; making a
skill usable (status active), editing and deleting are the user's, reached through the /skills routes.
Paths come from a validated uid and an integer id and are confined to the account folder before use. The
folder holds at most MAX_SKILLS small files, so every call reads it afresh (no cache to go stale).
shortcut: an id is max(existing)+1, so deleting the newest skill frees its number; upgrade to a counter file if a
stale `tool_skill_mark` for a deleted id ever matters.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from src.brain.files import BrainError, BrainFiles, _Account, _confine, _create_record, _has_home, _remove, _write
from src.brain.records import RecordError, header_line
from src.brain.search import Bm25Index, tokens
from src.clock import utcnow

SKILLS = ".skills"
MAX_TITLE, MAX_WHEN, MAX_STEPS, MAX_TOOLS = 80, 300, 1200, 200
MAX_ACTIVE, MAX_PROPOSED, MAX_SKILLS = 50, 20, 200
DEFAULT_LIMIT = 3
FAILING_MIN = 3
PROPOSED, ACTIVE, RETIRED = "proposed", "active", "retired"
STATUSES = (PROPOSED, ACTIVE, RETIRED)
SUCCESS, FAILURE = "success", "failure"
_FILE = re.compile(r"[1-9][0-9]{0,8}\.md")
_MAX_ID = 999_999_999
_MAX_FILE_BYTES = 16_384
_FENCE = "---"


@dataclass(frozen=True)
class Skill:
    id: int
    title: str
    when_to_use: str
    steps: str
    tools: str
    status: str
    successes: int
    failures: int
    created_at: str
    shared_from: str = ""

    @property
    def failing(self) -> bool:
        return self.failures >= FAILING_MIN and self.failures > self.successes


def _now() -> str:
    return utcnow().isoformat(timespec="seconds")


def _clean(label: str, text: object, limit: int, required: bool = True) -> str:
    clean = " ".join(str(text or "").split())
    if required and not clean:
        raise BrainError(422, f"The {label} is empty.")
    if len(clean) > limit:
        raise BrainError(422, f"The {label} is {len(clean)} characters; the limit is {limit}. Shorten it.")
    try:
        clean.encode("utf-8")
    except UnicodeError:
        raise BrainError(422, "Skill text must be valid UTF-8.") from None
    return clean


def _norm(title: str) -> str:
    return title.lower()


def render(skill: Skill) -> str:
    header = {
        "id": skill.id, "title": skill.title, "when_to_use": skill.when_to_use, "tools": skill.tools,
        "status": skill.status, "successes": skill.successes, "failures": skill.failures, "created_at": skill.created_at,
    }
    if skill.shared_from:
        header["shared_from"] = skill.shared_from
    lines = [_FENCE, *(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in header.items()), _FENCE, "", skill.steps]
    return "\n".join(lines) + "\n"


def parse(text: str, expected_id: int) -> Skill:
    text = text.replace("\r\n", "\n")
    if not text.startswith(_FENCE + "\n"):
        raise RecordError("No header.")
    head, closed, rest = text[len(_FENCE) + 1:].partition("\n" + _FENCE + "\n")
    if not closed:
        raise RecordError("The header is not closed.")
    values = dict(header_line(line) for line in head.split("\n") if line)
    steps = rest[1:] if rest.startswith("\n") else rest
    steps = steps[:-1] if steps.endswith("\n") else steps

    def text_of(key: str) -> str:
        value = values.get(key)
        if not isinstance(value, str):
            raise RecordError(f"{key} must be text.")
        return value

    def count_of(key: str) -> int:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RecordError(f"{key} must be a count.")
        return value

    if type(values.get("id")) is not int or values["id"] != expected_id:
        raise RecordError("The id does not match the file name.")
    status = text_of("status")
    if status not in STATUSES or not steps:
        raise RecordError("Unknown status or no steps.")
    try:
        title = _clean("title", text_of("title"), MAX_TITLE)
        when = _clean("when_to_use text", text_of("when_to_use"), MAX_WHEN)
        steps = _clean("steps", steps, MAX_STEPS)
        tools = _clean("tools list", text_of("tools"), MAX_TOOLS, required=False)
    except BrainError as error:
        raise RecordError(str(error)) from None
    shared_from = values.get("shared_from", "")
    if not isinstance(shared_from, str) or len(shared_from) > 80:
        raise RecordError("shared_from is not valid.")
    return Skill(expected_id, title, when, steps, tools, status, count_of("successes"), count_of("failures"),
                 text_of("created_at"), shared_from)


def _linked_folder(home: Path) -> bool:
    folder = home / SKILLS
    return folder.is_symlink() or folder.resolve() != home.resolve() / SKILLS


def _write_skill(root: Path, home: Path, path: Path, text: str, create: bool) -> None:
    if _linked_folder(home):
        raise BrainError(403, "That path is outside the skill folder.")
    write = _create_record if create else _write
    write(root, home, path, text)


def _read_all(root: Path, home: Path) -> tuple[dict[int, Skill], list[int]]:
    found: dict[int, Skill] = {}
    occupied: list[int] = []
    if not _has_home(root, home):
        return found, occupied
    folder = home / SKILLS
    if _linked_folder(home):
        return found, occupied
    _confine(root, home, folder)
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return found, occupied
    for name in names:
        if not _FILE.fullmatch(name):
            continue
        skill_id = int(name.removesuffix(".md"))
        occupied.append(skill_id)
        path = folder / name
        try:
            _confine(root, home, path)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                continue
            skill = parse(path.read_text(encoding="utf-8"), skill_id)
        except (BrainError, FileNotFoundError, UnicodeError, RecordError, RecursionError):
            continue
        found[skill.id] = skill
    return found, occupied


def _purge_skills(root: Path, home: Path) -> None:
    if not _has_home(root, home):
        return
    folder = home / SKILLS
    _confine(root, home, folder)
    if _linked_folder(home):
        raise BrainError(403, "That path is outside the skill folder.")
    if os.path.lexists(folder):
        shutil.rmtree(folder)


def _rank(candidates: list[Skill], query: str, limit: int) -> list[Skill]:
    if not tokens(query):
        return sorted(candidates, key=lambda skill: -skill.id)[:limit]
    by_id = {str(skill.id): skill for skill in candidates}
    index = Bm25Index({key: (s.title, f"{s.when_to_use} {s.steps}", s.tools) for key, s in by_id.items()})
    return [by_id[key] for key, _ in index.search(query, limit)]


class SkillFiles:
    def __init__(self, brain: BrainFiles) -> None:
        self._brain = brain

    async def _scan(self, home: Path) -> tuple[dict[int, Skill], list[int]]:
        return await asyncio.to_thread(_read_all, self._brain.root, home)

    async def _load(self, home: Path) -> dict[int, Skill]:
        skills, _ = await self._scan(home)
        return skills

    async def _save(self, account: _Account, home: Path, skill: Skill, *, create: bool = False) -> None:
        path = home / SKILLS / f"{skill.id}.md"
        await self._brain.mutate(account, _write_skill, self._brain.root, home, path, render(skill), create)

    @staticmethod
    def _same_title(skills: dict[int, Skill], title: str, *, except_id: int = 0) -> Skill | None:
        return next((s for s in skills.values() if s.id != except_id and s.status != RETIRED and _norm(s.title) == _norm(title)), None)

    async def propose(self, uid: str, title: str, when_to_use: str, steps: str, tools: str = "",
                      shared_from: str = "") -> tuple[Skill, bool]:
        title = _clean("title", title, MAX_TITLE)
        when_to_use = _clean("when_to_use text", when_to_use, MAX_WHEN)
        steps = _clean("steps", steps, MAX_STEPS)
        tools = _clean("tools list", tools, MAX_TOOLS, required=False)
        async with self._brain.locked(uid) as (home, account):
            skills, occupied = await self._scan(home)
            same = self._same_title(skills, title)
            if same is not None:
                if shared_from:
                    raise BrainError(409, "You already have a skill with that title.")
                return same, True
            self._check_proposal_room(skills)
            skill_id = max(occupied, default=0) + 1
            if len(occupied) >= MAX_SKILLS or skill_id > _MAX_ID:
                raise BrainError(409, "The skill list is full. The user must delete some skills first.")
            skill = Skill(skill_id, title, when_to_use, steps, tools, PROPOSED, 0, 0, _now(), shared_from)
            await self._save(account, home, skill, create=True)
            return skill, False

    async def search(self, uid: str, query: str = "", limit: int = DEFAULT_LIMIT) -> list[Skill]:
        async with self._brain.locked(uid) as (home, _):
            skills = await self._load(home)
        usable = [s for s in skills.values() if s.status == ACTIVE and not s.failing]
        return await asyncio.to_thread(_rank, usable, query, max(1, limit))

    async def list(self, uid: str) -> list[Skill]:
        async with self._brain.locked(uid) as (home, _):
            skills = await self._load(home)
        return sorted(skills.values(), key=lambda skill: -skill.id)

    @staticmethod
    def _check_proposal_room(skills: dict[int, Skill]) -> None:
        if sum(1 for s in skills.values() if s.status == PROPOSED) >= MAX_PROPOSED:
            raise BrainError(409, f"You already have {MAX_PROPOSED} skills waiting for approval. Ask the user to review them first.")

    async def set_status(self, uid: str, skill_id: int, status: str) -> Skill | None:
        if status not in STATUSES:
            raise BrainError(422, "That is not a valid skill status.")
        async with self._brain.locked(uid) as (home, account):
            skills = await self._load(home)
            skill = skills.get(skill_id)
            if skill is None:
                return None
            if status == ACTIVE and skill.status != ACTIVE and sum(1 for s in skills.values() if s.status == ACTIVE) >= MAX_ACTIVE:
                raise BrainError(409, f"You already have {MAX_ACTIVE} active skills. Retire one first.")
            if status == PROPOSED and skill.status != PROPOSED:
                self._check_proposal_room(skills)
            changed = replace(skill, status=status)
            await self._save(account, home, changed)
            return changed

    async def update(self, uid: str, skill_id: int, title: str, when_to_use: str, steps: str, tools: str = "") -> Skill | None:
        title = _clean("title", title, MAX_TITLE)
        when_to_use = _clean("when_to_use text", when_to_use, MAX_WHEN)
        steps = _clean("steps", steps, MAX_STEPS)
        tools = _clean("tools list", tools, MAX_TOOLS, required=False)
        async with self._brain.locked(uid) as (home, account):
            skills = await self._load(home)
            skill = skills.get(skill_id)
            if skill is None:
                return None
            if self._same_title(skills, title, except_id=skill_id) is not None:
                raise BrainError(409, "Another skill already has that title.")
            changed = replace(skill, title=title, when_to_use=when_to_use, steps=steps, tools=tools, successes=0, failures=0)
            await self._save(account, home, changed)
            return changed

    async def mark(self, uid: str, skill_id: int, outcome: str) -> Skill | None:
        if outcome not in (SUCCESS, FAILURE):
            raise BrainError(422, f"The outcome must be {SUCCESS!r} or {FAILURE!r}.")
        async with self._brain.locked(uid) as (home, account):
            skill = (await self._load(home)).get(skill_id)
            if skill is None or skill.status != ACTIVE:
                return None
            changed = replace(skill, successes=skill.successes + (outcome == SUCCESS), failures=skill.failures + (outcome == FAILURE))
            await self._save(account, home, changed)
            return changed

    async def delete(self, uid: str, skill_id: int) -> bool:
        async with self._brain.locked(uid) as (home, account):
            if skill_id not in await self._load(home):
                return False
            await self._brain.mutate(account, _remove, self._brain.root, home, home / SKILLS / f"{skill_id}.md")
            return True

    async def purge(self, uid: str) -> None:
        """Delete this account's skills only. Quiet when the brain already purged the account."""
        try:
            async with self._brain.locked(uid) as (home, account):
                await self._brain.mutate(account, _purge_skills, self._brain.root, home)
        except BrainError as error:
            if error.status != 404:
                raise
