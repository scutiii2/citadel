"""Per-user learned skills: reusable how-tos an agent proposes and the user approves."""

from starlette.applications import Starlette

from src.services.capability_base import Capability


class Skills(Capability):
    id = "skills"
    label = "Skills"

    def install_routes(self, app: Starlette) -> None:
        from src.capabilities.skills.routes import install_skill_routes

        install_skill_routes(app)


CAPABILITY = Skills()
