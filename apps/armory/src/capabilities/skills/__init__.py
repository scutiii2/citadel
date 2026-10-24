"""Per-user learned skills: reusable how-tos an agent proposes and the user approves."""
from src.services import capability_meta

META = capability_meta.register(folder="skills", id="skills", label="Skills")
