"""Allegro parcel tracker custom component for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.start import async_at_started

from .account.client import AllegroClient
from .account.errors import AllegroApiError, AllegroAuthError
from .const import CONF_COOKIE, DOMAIN, PLATFORMS
from .contents import ContentsStore
from .coordinator import AllegroCoordinator
from .handoff import HandOff, async_clear_issues
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


@dataclass
class AllegroData:
    """Runtime data attached to an Allegro config entry."""

    client: AllegroClient
    coordinator: AllegroCoordinator
    login: str
    session: aiohttp.ClientSession


type AllegroConfigEntry = ConfigEntry[AllegroData]


async def async_setup_entry(hass: HomeAssistant, entry: AllegroConfigEntry) -> bool:
    """Set up Allegro from a config entry."""
    # The cookie goes out as an explicit header; a jar that never stores
    # anything keeps cookies Allegro sets from leaking between two accounts.
    # The connector is reused (connector_owner=False) so this stays cheap.
    session = aiohttp.ClientSession(
        connector=async_get_clientsession(hass).connector,
        connector_owner=False,
        cookie_jar=aiohttp.DummyCookieJar(),
    )
    client = AllegroClient(entry.data[CONF_COOKIE], session)

    try:
        login = await client.async_get_login()
    except AllegroAuthError as err:
        # The cookie expired — ask for a new one instead of retrying forever.
        await session.close()
        raise ConfigEntryAuthFailed("Allegro session cookie rejected") from err
    except (AllegroApiError, aiohttp.ClientError) as err:
        # Non-auth failure (outage, bot page) — retry with backoff.
        await session.close()
        raise ConfigEntryNotReady("Allegro is not reachable") from err

    coordinator = AllegroCoordinator(hass, client, entry)
    await coordinator.contents_store.async_load()

    try:
        # First refresh here, before forwarding to platforms, so a transient
        # failure fails the whole entry and HA retries it with backoff.
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # Without this, every setup retry leaks a session.
        await session.close()
        raise

    entry.runtime_data = AllegroData(
        client=client, coordinator=coordinator, login=login, session=session
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await session.close()
        raise

    async_setup_services(hass)

    if hass.state is not CoreState.running:
        # During startup a courier may not have registered track_parcel
        # yet, which would read as "not installed".
        async def _hand_off(_: HomeAssistant) -> None:
            await coordinator.async_hand_off_after_start()

        entry.async_on_unload(async_at_started(hass, _hand_off))

    # No entry.add_update_listener: the options flow is an
    # OptionsFlowWithReload, which may not be combined with one.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AllegroConfigEntry) -> bool:
    """Unload an Allegro config entry."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.session.close()
        # The services are shared by every account, so they go with the last one.
        if not any(
            other.state is ConfigEntryState.LOADED
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        ):
            async_unload_services(hass)
        return True
    return False


async def async_remove_entry(hass: HomeAssistant, entry: AllegroConfigEntry) -> None:
    """Forget what this entry stored: hand-offs and user contents."""
    await HandOff(hass, entry.entry_id, entry.options).async_remove()
    await ContentsStore(hass, entry.entry_id).async_remove()
    # The courier issues are shared by every entry; the last one clears them.
    if not hass.config_entries.async_entries(DOMAIN):
        async_clear_issues(hass)
