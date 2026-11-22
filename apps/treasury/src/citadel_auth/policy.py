"""Explicit receiver policy. Prefixes match complete path segments."""

from dataclasses import dataclass

SERVICES = frozenset({"portcullis", "stronghold", "legion", "armory", "treasury"})


@dataclass(frozen=True)
class Rule:
    prefixes: tuple[str, ...]
    forwards_requester: bool = False


POLICY = {
    "stronghold": {
        "portcullis": Rule(("/",), True),
        "legion": Rule(("/mcp",), True),
    },
    "armory": {
        "portcullis": Rule(("/mcp", "/upload", "/download", "/media", "/pdf", "/admin", "/capabilities", "/extensions", "/commands", "/tickets/tags", "/connections"), True),
        "stronghold": Rule(("/mcp", "/skills", "/memory", "/tickets", "/ticket-admin", "/upload", "/connections"), True),
        "legion": Rule(("/mcp",), True),
    },
    "legion": {
        "armory": Rule(("/mcp",), True),
        "portcullis": Rule(("/mcp", "/registry", "/agents"), True),
        "stronghold": Rule(("/mcp", "/registry", "/agents"), True),
        "legion": Rule(("/mcp",), True),
    },
    "treasury": {
        **{name: Rule(("/",)) for name in ("portcullis", "stronghold", "legion", "armory")},
        "treasury": Rule(("/outside",)),
    },
    "portcullis": {"stronghold": Rule(("/internal",))},
}


def allowed(audience: str, caller: str, path: str) -> bool:
    rule = POLICY.get(audience, {}).get(caller)
    return bool(rule and (path == "/ready" or any(
        prefix == "/" or path == prefix or path.startswith(prefix + "/") for prefix in rule.prefixes
    )))


def may_forward(audience: str, caller: str) -> bool:
    rule = POLICY.get(audience, {}).get(caller)
    return bool(rule and rule.forwards_requester)
