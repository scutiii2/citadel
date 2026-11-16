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
        "armory": Rule(("/brains/resolve", "/notes", "/memory", "/skills", "/tickets"), True),
    },
    "armory": {
        "portcullis": Rule(("/mcp", "/upload", "/download", "/media", "/admin", "/capabilities", "/extensions"), True),
        "stronghold": Rule(("/mcp", "/skills", "/memory", "/notes", "/tickets"), True),
        "legion": Rule(("/mcp",), True),
    },
    "legion": {
        "portcullis": Rule(("/mcp", "/registry", "/agents"), True),
        "stronghold": Rule(("/mcp", "/registry"), True),
    },
    "treasury": {name: Rule(("/",)) for name in ("portcullis", "stronghold", "legion", "armory")},
    "portcullis": {"stronghold": Rule(("/internal",))},
}


def allowed(audience: str, caller: str, path: str) -> bool:
    rule = POLICY.get(audience, {}).get(caller)
    return bool(rule and any(prefix == "/" or path == prefix or path.startswith(prefix + "/")
                             for prefix in rule.prefixes))


def may_forward(audience: str, caller: str) -> bool:
    rule = POLICY.get(audience, {}).get(caller)
    return bool(rule and rule.forwards_requester)
