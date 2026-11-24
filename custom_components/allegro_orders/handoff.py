"""Hand parcels over to the suite's courier integrations (ported from ha-amazon).

Allegro is a shop: it knows what was bought, the courier knows where the
parcel is. Handing the waybill to the courier's own integration gives the user
its delivery window, pickup point and history. Unlike ha-amazon, the parcel
stays listed here too; the aggregator dedupes on (carrier, barcode), and this
integration lists Allegro as a shop so the courier's record wins.
Allegro One parcels and couriers without a suite integration are never handed off.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .account.parcels import hand_off_domain
from .const import (
    ALLEGRO_CARRIERS,
    CONF_CONTENTS,
    CONF_HAND_OFF,
    CONF_TRACKING_CODE,
    DEFAULT_HAND_OFF,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SERVICE_TRACK_PARCEL = "track_parcel"
DOCS_CARRIERS_URL = "https://ha-parcel-integrations.github.io/carriers/"

# The order page lists only the latest orders, so a code missing from one poll
# is forgotten only once it is old enough to be truly gone.
FORGET_AFTER = timedelta(days=30)

# domain -> courier name as the suite publishes it
_COURIERS = {domain: name for name, domain in ALLEGRO_CARRIERS.values() if domain}


def issue_id(carrier_domain: str) -> str:
    """One Repair issue per courier domain, shared by every Allegro entry."""
    return f"carrier_not_set_up_{carrier_domain}"


def async_clear_issues(hass: HomeAssistant) -> None:
    """Drop every courier issue, once no Allegro entry is left to need one."""
    for domain in _COURIERS:
        ir.async_delete_issue(hass, DOMAIN, issue_id(domain))


class HandOff:
    """Per-entry hand-off state: what was handed over, and the calls to do it."""

    def __init__(self, hass: HomeAssistant, entry_id: str, options: Any) -> None:
        """Remember the entry; the stored state is read on first use."""
        self._hass = hass
        self._options = options
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.hand_off.{entry_id}"
        )
        self._loaded = False
        # code -> {"domain": courier domain, "since": ISO time of the hand-off}
        self._handed: dict[str, dict[str, str]] = {}
        # Codes that already failed this session; retried only after a reload.
        self._failed: set[str] = set()

    @property
    def _started(self) -> bool:
        """Whether Home Assistant is done starting (couriers registered services)."""
        return self._hass.state is CoreState.running

    @property
    def enabled(self) -> bool:
        """Whether the user wants parcels handed off."""
        return bool(self._options.get(CONF_HAND_OFF, DEFAULT_HAND_OFF))

    async def _load(self) -> None:
        if self._loaded:
            return
        stored = await self._store.async_load() or {}
        self._handed = dict(stored.get("handed", {}))
        self._loaded = True

    async def _save(self) -> None:
        await self._store.async_save({"handed": self._handed})

    async def async_remove(self) -> None:
        """Forget the stored state when the entry is removed."""
        await self._store.async_remove()

    async def _call(self, domain: str, data: dict[str, str]) -> None:
        await self._hass.services.async_call(
            domain, SERVICE_TRACK_PARCEL, data, blocking=True
        )

    async def _track(self, domain: str, code: str, contents: str | None) -> bool:
        """Hand a code to the courier; ``False`` when it refused it."""
        data = {CONF_TRACKING_CODE: code}
        try:
            try:
                await self._call(
                    domain, {**data, CONF_CONTENTS: contents} if contents else data
                )
            except vol.Invalid:
                if not contents:
                    raise
                # Not every courier's track_parcel takes contents (InPost does not).
                await self._call(domain, data)
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning(
                "The %s integration did not accept tracking code %s (%s)."
                " Add it there by hand if you want it tracked by %s; it stays"
                " listed here until then.",
                domain,
                code,
                err,
                domain,
            )
            return False
        return True

    def _sync_issues(self, needed: set[str]) -> None:
        """Raise an issue for a missing courier; clear it once the courier is there.

        An issue is never cleared because its parcels went away: a user who
        ignored it would be nagged again by the next such parcel.
        """
        for domain, name in _COURIERS.items():
            if self._hass.services.has_service(domain, SERVICE_TRACK_PARCEL):
                ir.async_delete_issue(self._hass, DOMAIN, issue_id(domain))
            elif domain in needed:
                url = f"{DOCS_CARRIERS_URL}#{domain.replace('_', '-')}"
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    issue_id(domain),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="carrier_not_set_up",
                    translation_placeholders={"carrier": name, "url": url},
                    learn_more_url=url,
                )

    async def async_process(self, parcels: list[dict]) -> None:
        """Hand every not-yet-handed, undelivered courier parcel over once."""
        await self._load()

        if not self.enabled:
            if self._handed:
                self._handed = {}
                await self._save()
            return

        changed = False
        needed: set[str] = set()
        for parcel in parcels:
            code = parcel.get("barcode")
            target = hand_off_domain(parcel)
            if (
                target is None
                or not code
                or code in self._handed
                or code in self._failed
                or parcel["delivered"]
                or not self._started
            ):
                continue
            if not self._hass.services.has_service(target, SERVICE_TRACK_PARCEL):
                needed.add(target)
            elif await self._track(target, code, parcel.get("contents")):
                self._handed[code] = {
                    "domain": target,
                    "since": dt_util.utcnow().isoformat(),
                }
                changed = True
            else:
                self._failed.add(code)

        seen = {p.get("barcode") for p in parcels}
        cutoff = dt_util.utcnow() - FORGET_AFTER
        stale = [
            code
            for code, handed in self._handed.items()
            if code not in seen
            and (since := dt_util.parse_datetime(handed["since"])) is not None
            and since < cutoff
        ]
        for code in stale:
            del self._handed[code]
            changed = True

        if self._started:
            self._sync_issues(needed)
        if changed:
            await self._save()
