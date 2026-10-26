"""Shared outgoing email and threaded replies."""

from src.services.capability_base import Capability


class Email(Capability):
    id = "email"
    label = "Email"


CAPABILITY = Email()
