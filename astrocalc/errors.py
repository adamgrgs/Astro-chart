"""Explicit, machine-readable error types.

Every failure the calculator can hit is surfaced as a ChartError with a stable
`code`, a human message, and optional `details` (e.g. the two candidate UTC
offsets for an ambiguous local time). Nothing is silently guessed.
"""
from __future__ import annotations

from typing import Any


class ChartError(Exception):
    #: HTTP status used by the API layer
    status = 422

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        if status is not None:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


# Stable error codes (documented in docs/API.md)
INVALID_INPUT = "INVALID_INPUT"
UNSUPPORTED_DATE = "UNSUPPORTED_DATE"
AMBIGUOUS_LOCAL_TIME = "AMBIGUOUS_LOCAL_TIME"
NONEXISTENT_LOCAL_TIME = "NONEXISTENT_LOCAL_TIME"
UNKNOWN_TIMEZONE = "UNKNOWN_TIMEZONE"
MISSING_EPHEMERIS = "MISSING_EPHEMERIS"
EPHEMERIS_ERROR = "EPHEMERIS_ERROR"
HOUSE_SYSTEM_FAILED = "HOUSE_SYSTEM_FAILED"
PLACE_NOT_FOUND = "PLACE_NOT_FOUND"
GEOCODER_UNAVAILABLE = "GEOCODER_UNAVAILABLE"
AYANAMSA_REQUIRED = "AYANAMSA_REQUIRED"
