class NotFoundError(Exception):
    """Raised when a desired object could not be found, for example, a libvirt domain."""

    pass


class Conflict(Exception):
    """Raised in case of a conflict, for example, when a user wants to create a volume if a volume with the same name
    already exists."""

    pass


class ProgramError(Exception):
    """Raised when an external program failed."""

    pass


class IllegalStateError(Exception):
    """Raised when an operation cannot be performed because an object is not in the required state."""

    pass
