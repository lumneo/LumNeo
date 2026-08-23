"""Deterministic fault controls shared by simulated Hardware drivers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FaultProfile:
    offline: bool = False
    delay_ms: int = 0
    timeout: bool = False
    driver_error: str | None = None
    invalid_output: bool = False
    fail_next_n: int = 0

    def __post_init__(self) -> None:
        for field_name in ("offline", "timeout", "invalid_output"):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a bool")
        if type(self.delay_ms) is not int or self.delay_ms < 0:
            raise ValueError("delay_ms must be a non-negative integer")
        if self.driver_error is not None and not isinstance(self.driver_error, str):
            raise TypeError("driver_error must be a string or None")
        if type(self.fail_next_n) is not int or self.fail_next_n < 0:
            raise ValueError("fail_next_n must be a non-negative integer")

    def consume_fail_next(self) -> bool:
        if self.fail_next_n <= 0:
            return False
        self.fail_next_n -= 1
        return True


__all__ = ("FaultProfile",)
