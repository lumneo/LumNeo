"""Reliability signals for physical execution outcome classification."""

from __future__ import annotations


class ConfirmedNotExecutedTimeout(TimeoutError):
    """The adapter confirms the operation did not successfully execute.

    A local wait deadline must not raise this signal on its own.  It is reserved
    for adapters that have protocol/device evidence that execution did not occur.
    """


__all__ = ("ConfirmedNotExecutedTimeout",)
