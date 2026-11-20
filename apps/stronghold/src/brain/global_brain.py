"""The global brain: one shared long-term folder (files and skills) that every account and agent reads.

It is a second BrainFiles/SkillFiles pair under <brain root>/_global with the fixed account id `global`, so every rule of
the personal brain applies (confinement, records, revert, quotas, search). Writing needs the brain.global.write permission,
checked by the routes; agents have no tool that writes here.
"""

from __future__ import annotations

from pathlib import Path

from src.brain.files import BrainFiles
from src.brain.limits import LongTermLimits
from src.brain.skills import SkillFiles

GLOBAL_UID = "global"


class GlobalBrain:
    def __init__(self, folder: Path, limits: LongTermLimits) -> None:
        self.files = BrainFiles(Path(folder) / "_global", limits)
        self.skills = SkillFiles(self.files)
