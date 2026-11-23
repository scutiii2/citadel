"""Kind handlers supply prompts and validation to the shared pipeline."""

from src.agents.roles.architect.code import CodeArchitect
from src.agents.roles.architect.task import TaskArchitect


KINDS = {"code": CodeArchitect(), "task": TaskArchitect()}
