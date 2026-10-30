"""Kind handlers supply prompts and validation to the shared pipeline."""

from src.agents.roles.architect.code import CodeArchitect


KINDS = {"code": CodeArchitect()}
