"""Generator: random passwords, passphrases, PINs and one-time codes, plus
TOTP secrets and the current TOTP code for a secret."""

from src.services.capability_base import Capability


class Generator(Capability):
    id = "gen"
    label = "Generator"


CAPABILITY = Generator()
