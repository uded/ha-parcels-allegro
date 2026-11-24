"""Client for Allegro's buyer web API, authenticated by the QXLSESSID cookie.

These endpoints are undocumented; they are the ones allegro.pl itself calls.
``aiohttp.ClientError`` propagates untouched: the coordinator turns it into
``UpdateFailed``.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .errors import AllegroApiError, AllegroAuthError
from .parcels import join_parcels

USERS_URL = "https://api.allegro.pl/users"
ORDERS_URL = "https://api.allegro.pl/myorder-api/myorders?limit=25"
PACKAGES_URL = "https://edge.allegro.pl/packages"

_ACCEPT = {
    USERS_URL: "application/vnd.allegro.public.v2+json",
    ORDERS_URL: "application/vnd.allegro.public.v3+json",
    PACKAGES_URL: "application/vnd.allegro.internal.v1+json",
}


class AllegroClient:
    """Reads the logged-in buyer's account, orders and packages."""

    def __init__(self, cookie: str, session: aiohttp.ClientSession) -> None:
        """Keep the cookie value and the shared session."""
        self._cookie = cookie
        self._session = session

    async def _get(self, url: str) -> dict[str, Any]:
        headers = {
            "Cookie": f"QXLSESSID={self._cookie}",
            "Referer": "https://allegro.pl/",
            "Accept": _ACCEPT[url],
        }
        # No redirects: an expired session answers with a 302 to the login page.
        async with self._session.get(
            url, headers=headers, allow_redirects=False
        ) as response:
            status = response.status
            if status in (401, 403):
                raise AllegroAuthError(f"HTTP {status}", status_code=status)
            if 300 <= status < 400:
                if "login" in response.headers.get("Location", ""):
                    raise AllegroAuthError("redirect to login", status_code=status)
                raise AllegroApiError(f"HTTP {status}", status_code=status)
            if status == 429:
                raise AllegroApiError(
                    "HTTP 429",
                    status_code=429,
                    retry_after=_retry_after(response.headers.get("Retry-After")),
                )
            if status != 200:
                raise AllegroApiError(f"HTTP {status}", status_code=status)
            if "json" not in response.headers.get("Content-Type", ""):
                # Bot protection serves an HTML page with 200.
                raise AllegroApiError("not JSON (bot protection page?)")
            try:
                payload = await response.json(content_type=None)
            except ValueError as err:
                raise AllegroApiError("unparseable body") from err
        if not isinstance(payload, dict):
            raise AllegroApiError("unexpected body (not a JSON object)")
        return payload

    async def async_get_login(self) -> str:
        """Return the account login, used as the config entry's unique id."""
        payload = await self._get(USERS_URL)
        login = payload.get("accounts", {}).get("allegro", {}).get("login")
        if not isinstance(login, str) or not login:
            raise AllegroApiError("unexpected body (no login)")
        return login

    async def async_get_orders(self) -> list[dict[str, Any]]:
        """Return every order of the latest checkouts, each tagged with its groupId."""
        payload = await self._get(ORDERS_URL)
        groups = payload.get("orderGroups")
        if not isinstance(groups, list):
            raise AllegroApiError("unexpected body (no orderGroups)")
        return [
            {**order, "groupId": group.get("groupId")}
            for group in groups
            if isinstance(group, dict)
            for order in group.get("myorders") or []
            if isinstance(order, dict)
        ]

    async def async_get_packages(self) -> list[dict[str, Any]]:
        """Return the active packages from "Moje przesyłki"."""
        payload = await self._get(PACKAGES_URL)
        packages = payload.get("packages")
        if not isinstance(packages, list):
            raise AllegroApiError("unexpected body (no packages)")
        return [package for package in packages if isinstance(package, dict)]

    async def async_get_parcels(self) -> list[dict[str, Any]]:
        """Return one raw parcel per waybill (see ``parcels.join_parcels``)."""
        orders = await self.async_get_orders()
        packages = await self.async_get_packages()
        return join_parcels(orders, packages)


def _retry_after(header: str | None) -> float | None:
    """Seconds from ``Retry-After``; an HTTP-date falls back to our own backoff."""
    try:
        return float(header) if header else None
    except ValueError:
        return None
