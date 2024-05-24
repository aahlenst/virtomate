"""Matchers that simplify writing pytest assertions."""

from typing import Any


class _AnyStr:
    """A helper class that compares equal to any string."""

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, str)

    def __repr__(self) -> str:
        return "<AnyStr>"


ANY_STR = _AnyStr()
"""A helper object that compares equal to any string."""


class _AnyInt:
    """A helper class that compares equal to any int."""

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, int)

    def __repr__(self) -> str:
        return "<AnyInt>"


ANY_INT = _AnyInt()
"""A helper object that compares equal to any int."""
