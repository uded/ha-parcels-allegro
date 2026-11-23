"""Errors raised by the Allegro account client."""

from __future__ import annotations


class AllegroApiError(Exception):
    """An Allegro request failed for a non-auth reason (outage, 429, bot page)."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the status code and the ``Retry-After`` seconds, if any."""
        super().__init__(f"Allegro request failed: {detail}")
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class AllegroAuthError(AllegroApiError):
    """Allegro rejected the session cookie; only this one may start reauth."""
