"""The two kinds of failure: worth retrying, and not."""

from __future__ import annotations


class PlacesError(RuntimeError):
    """A request failed in a way that will not be fixed by retrying."""


class RetryableError(RuntimeError):
    """Transient failure: rate limit, server error or connection problem."""
