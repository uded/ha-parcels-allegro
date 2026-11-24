"""Tests for the Allegro config, reauth and options flow (QXLSESSID cookie)."""

from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.config_entries import SOURCE_USER
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.allegro_orders.account.errors import (
    AllegroApiError,
    AllegroAuthError,
)
from custom_components.allegro_orders.const import (
    CONF_COOKIE,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_HAND_OFF,
    DOMAIN,
)

from .payloads import active_sample

LOGIN = "buyer_login"
COOKIE = "cookie-value"
CLIENT = "custom_components.allegro_orders.account.client.AllegroClient"
GET_LOGIN = f"{CLIENT}.async_get_login"


def _entry(login: str = LOGIN) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=login,
        unique_id=login,
        data={CONF_COOKIE: COOKIE},
        options={
            CONF_DELIVERED_FILTER_TYPE: "days",
            CONF_DELIVERED_FILTER_AMOUNT: 7,
            CONF_HAND_OFF: True,
        },
    )


async def test_user_step_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"

    with patch(GET_LOGIN, new=AsyncMock(return_value=LOGIN)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: f"  {COOKIE}\n"}
        )

    assert result["type"] == "create_entry"
    assert result["title"] == LOGIN
    assert result["result"].unique_id == LOGIN
    # Pasted whitespace is trimmed before it is stored.
    assert result["data"] == {CONF_COOKIE: COOKIE}
    assert result["options"][CONF_HAND_OFF] is True


async def test_user_step_accepts_the_whole_cookie_pair(hass):
    """Copying "QXLSESSID=value" from dev tools must work too."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(GET_LOGIN, new=AsyncMock(return_value=LOGIN)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: f"QXLSESSID={COOKIE}"}
        )
    assert result["data"] == {CONF_COOKIE: COOKIE}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AllegroAuthError("HTTP 401"), "invalid_auth"),
        (AllegroApiError("HTTP 500"), "cannot_connect"),
        (aiohttp.ClientError("boom"), "cannot_connect"),
    ],
)
async def test_user_step_surfaces_errors(hass, error, expected):
    """A rejected cookie and an outage must not look the same to the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(GET_LOGIN, new=AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: COOKIE}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": expected}


async def test_duplicate_account_aborts(hass):
    _entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(GET_LOGIN, new=AsyncMock(return_value=LOGIN)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "another-cookie"}
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_reauth_updates_cookie(hass):
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(GET_LOGIN, new=AsyncMock(return_value=LOGIN)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "new-cookie"}
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_COOKIE] == "new-cookie"


async def test_reauth_rejects_a_different_account(hass):
    """A cookie from another Allegro account must not silently rebind the entry."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(GET_LOGIN, new=AsyncMock(return_value="someone_else")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "new-cookie"}
        )

    assert result["type"] == "abort"
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_COOKIE] == COOKIE


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AllegroAuthError("HTTP 401"), "invalid_auth"),
        (AllegroApiError("HTTP 500"), "cannot_connect"),
    ],
)
async def test_reauth_surfaces_errors(hass, error, expected):
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(GET_LOGIN, new=AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_COOKIE: "new-cookie"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": expected}


async def test_options_flow_reloads_with_the_new_options(hass):
    entry = _entry()
    entry.add_to_hass(hass)

    seen = []
    real_schedule = hass.config_entries.async_schedule_reload

    def _record(entry_id):
        seen.append(dict(entry.options))
        return real_schedule(entry_id)

    with (
        patch(GET_LOGIN, new=AsyncMock(return_value=LOGIN)),
        patch(
            f"{CLIENT}.async_get_parcels",
            new=AsyncMock(return_value=[active_sample()]),
        ),
        patch.object(hass.config_entries, "async_schedule_reload", side_effect=_record),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "delivered": {
                    CONF_DELIVERED_FILTER_TYPE: "parcels",
                    CONF_DELIVERED_FILTER_AMOUNT: 5,
                },
                "hand_off": {CONF_HAND_OFF: False},
            },
        )
        await hass.async_block_till_done()

    expected = {
        CONF_DELIVERED_FILTER_TYPE: "parcels",
        CONF_DELIVERED_FILTER_AMOUNT: 5,
        CONF_HAND_OFF: False,
    }
    assert result["type"] == "create_entry"
    assert result["data"] == expected
    assert seen == [expected]
