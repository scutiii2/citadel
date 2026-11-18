"""Short, token-free authentication failures."""


class AuthError(ValueError):
    """A credential could not be authenticated."""


class Forbidden(AuthError):
    """An authenticated caller lacks permission."""
