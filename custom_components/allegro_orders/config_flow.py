"""Config flow for the Allegro parcel tracker integration.

Auth is the allegro.pl session cookie (QXLSESSID): Allegro has no buyer API
and its login form sits behind 2FA and captcha.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .account.client import AllegroClient
from .account.errors import AllegroApiError, AllegroAuthError
from .const import (
    CONF_COOKIE,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_HAND_OFF,
    DEFAULT_DELIVERED_FILTER_AMOUNT,
    DEFAULT_DELIVERED_FILTER_TYPE,
    DEFAULT_HAND_OFF,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_COOKIE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_COOKIE): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    }
)


def _clean_cookie(value: str) -> str:
    """Accept the bare value or a pasted ``QXLSESSID=value`` pair."""
    value = value.strip()
    if value.startswith("QXLSESSID="):
        value = value.removeprefix("QXLSESSID=").split(";", 1)[0].strip()
    return value


class AllegroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI-driven configuration flow for the Allegro integration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> AllegroOptionsFlowHandler:
        """Return the options flow handler."""
        return AllegroOptionsFlowHandler()

    async def _login(self, user_input: dict[str, Any], errors: dict[str, str]):
        """Return ``(cookie, login)``, or ``None`` with ``errors`` filled in."""
        cookie = _clean_cookie(user_input[CONF_COOKIE])
        client = AllegroClient(cookie, async_get_clientsession(self.hass))
        try:
            return cookie, await client.async_get_login()
        except AllegroAuthError:
            errors["base"] = "invalid_auth"
        except (AllegroApiError, aiohttp.ClientError):
            errors["base"] = "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the cookie and validate it on submit."""
        errors: dict[str, str] = {}
        if user_input is not None and (result := await self._login(user_input, errors)):
            cookie, login = result
            await self.async_set_unique_id(login)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=login,
                data={CONF_COOKIE: cookie},
                options={
                    CONF_DELIVERED_FILTER_TYPE: DEFAULT_DELIVERED_FILTER_TYPE,
                    CONF_DELIVERED_FILTER_AMOUNT: DEFAULT_DELIVERED_FILTER_AMOUNT,
                    CONF_HAND_OFF: DEFAULT_HAND_OFF,
                },
            )
        return self.async_show_form(
            step_id="user", data_schema=_COOKIE_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth after the cookie stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh cookie and update the existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None and (result := await self._login(user_input, errors)):
            cookie, login = result
            # Another account's cookie must abort, not rebind this entry.
            await self.async_set_unique_id(login)
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates={CONF_COOKIE: cookie}
            )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_COOKIE_SCHEMA, errors=errors
        )


class AllegroOptionsFlowHandler(OptionsFlowWithReload):
    """Manage delivered retention and hand-off in one sectioned form."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and handle the single sectioned options form."""
        if user_input is not None:
            delivered = user_input["delivered"]
            # OptionsFlowWithReload reloads once the new options are saved; a
            # reload scheduled here would start before that, on the old ones.
            return self.async_create_entry(
                title="",
                data={
                    CONF_DELIVERED_FILTER_TYPE: delivered[CONF_DELIVERED_FILTER_TYPE],
                    CONF_DELIVERED_FILTER_AMOUNT: int(
                        delivered[CONF_DELIVERED_FILTER_AMOUNT]
                    ),
                    CONF_HAND_OFF: bool(user_input["hand_off"][CONF_HAND_OFF]),
                },
            )

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required("delivered"): section(
                    vol.Schema(
                        {
                            vol.Required(
                                CONF_DELIVERED_FILTER_TYPE,
                                default=current.get(
                                    CONF_DELIVERED_FILTER_TYPE,
                                    DEFAULT_DELIVERED_FILTER_TYPE,
                                ),
                            ): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=["days", "parcels"],
                                    translation_key=CONF_DELIVERED_FILTER_TYPE,
                                    mode=selector.SelectSelectorMode.LIST,
                                )
                            ),
                            vol.Required(
                                CONF_DELIVERED_FILTER_AMOUNT,
                                default=current.get(
                                    CONF_DELIVERED_FILTER_AMOUNT,
                                    DEFAULT_DELIVERED_FILTER_AMOUNT,
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=1,
                                    max=365,
                                    step=1,
                                    mode=selector.NumberSelectorMode.BOX,
                                )
                            ),
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required("hand_off"): section(
                    vol.Schema(
                        {
                            vol.Required(
                                CONF_HAND_OFF,
                                default=current.get(CONF_HAND_OFF, DEFAULT_HAND_OFF),
                            ): selector.BooleanSelector(),
                        }
                    ),
                    {"collapsed": False},
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
