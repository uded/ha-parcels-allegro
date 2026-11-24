"""Tests for the Allegro account client (cookie-authenticated web API)."""

import json
from pathlib import Path

import aiohttp
import pytest

from custom_components.allegro_orders.account.client import (
    ORDERS_URL,
    PACKAGES_URL,
    USERS_URL,
    AllegroClient,
)
from custom_components.allegro_orders.account.errors import (
    AllegroApiError,
    AllegroAuthError,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
COOKIE = "cookie-value"
ACCEPT = {
    USERS_URL: "application/vnd.allegro.public.v2+json",
    ORDERS_URL: "application/vnd.allegro.public.v3+json",
    PACKAGES_URL: "application/vnd.allegro.internal.v1+json",
}
JSON = {"Content-Type": "application/json"}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
async def client(hass, aioclient_mock):
    session = aioclient_mock.create_session(hass.loop)
    yield AllegroClient(COOKIE, session)
    await session.close()


async def test_get_login(client, aioclient_mock):
    aioclient_mock.get(USERS_URL, json=_fixture("users"), headers=JSON)
    assert await client.async_get_login() == "FAKE-login-0"


async def test_get_orders_flattens_groups(client, aioclient_mock):
    payload = _fixture("myorders")
    aioclient_mock.get(ORDERS_URL, json=payload, headers=JSON)
    orders = await client.async_get_orders()
    expected = [
        (group["groupId"], order["id"])
        for group in payload["orderGroups"]
        for order in group["myorders"]
    ]
    assert [(o["groupId"], o["id"]) for o in orders] == expected
    assert len(orders) == 25


async def test_orders_for_a_logged_out_view_raise_auth_error(client, aioclient_mock):
    """An expired session may answer 200 with an anonymous view and no orders."""
    aioclient_mock.get(
        ORDERS_URL, json={"orderGroups": [], "viewMode": "ANONYMOUS"}, headers=JSON
    )
    with pytest.raises(AllegroAuthError):
        await client.async_get_orders()


async def test_get_packages(client, aioclient_mock):
    aioclient_mock.get(PACKAGES_URL, json=_fixture("packages"), headers=JSON)
    packages = await client.async_get_packages()
    assert len(packages) == 5
    assert packages[0]["delivery"]["carrierId"] == "ALLEGRO"


async def test_get_parcels_joins_orders_and_packages(client, aioclient_mock):
    aioclient_mock.get(ORDERS_URL, json=_fixture("myorders"), headers=JSON)
    aioclient_mock.get(PACKAGES_URL, json=_fixture("packages"), headers=JSON)
    raws = await client.async_get_parcels()
    assert len(raws) == 24
    assert sum(raw["package"] is not None for raw in raws) == 5
    assert set(raws[0]) == {"waybill", "carrier_id", "order", "package"}


async def test_requests_send_cookie_accept_and_referer(client, aioclient_mock):
    aioclient_mock.get(USERS_URL, json=_fixture("users"), headers=JSON)
    aioclient_mock.get(ORDERS_URL, json=_fixture("myorders"), headers=JSON)
    aioclient_mock.get(PACKAGES_URL, json=_fixture("packages"), headers=JSON)
    await client.async_get_login()
    await client.async_get_orders()
    await client.async_get_packages()
    assert len(aioclient_mock.mock_calls) == 3
    for _method, url, _data, headers in aioclient_mock.mock_calls:
        assert headers["Cookie"] == f"QXLSESSID={COOKIE}"
        assert headers["Referer"] == "https://allegro.pl/"
        assert headers["Accept"] == ACCEPT[str(url)]


@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (401, {}),
        (403, {}),
        (302, {"Location": "https://allegro.pl/login/auth?origin_url=%2F"}),
    ],
)
async def test_auth_failure_raises(client, aioclient_mock, status, headers):
    aioclient_mock.get(ORDERS_URL, status=status, headers=headers)
    with pytest.raises(AllegroAuthError):
        await client.async_get_orders()


async def test_redirect_elsewhere_is_api_error_not_auth(client, aioclient_mock):
    aioclient_mock.get(
        ORDERS_URL, status=302, headers={"Location": "https://allegro.pl/maintenance"}
    )
    with pytest.raises(AllegroApiError) as err:
        await client.async_get_orders()
    assert not isinstance(err.value, AllegroAuthError)


async def test_html_body_raises_api_error(client, aioclient_mock):
    """Bot protection answers 200 with an HTML page; that is an outage, not data."""
    aioclient_mock.get(
        PACKAGES_URL,
        text="<html>captcha</html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    with pytest.raises(AllegroApiError) as err:
        await client.async_get_packages()
    assert not isinstance(err.value, AllegroAuthError)


async def test_unexpected_shape_raises(client, aioclient_mock):
    aioclient_mock.get(ORDERS_URL, json={"nothing": []}, headers=JSON)
    with pytest.raises(AllegroApiError):
        await client.async_get_orders()


@pytest.mark.parametrize("status", [500, 502])
async def test_outage_is_api_error(client, aioclient_mock, status):
    aioclient_mock.get(USERS_URL, status=status)
    with pytest.raises(AllegroApiError) as err:
        await client.async_get_login()
    assert err.value.status_code == status
    assert not isinstance(err.value, AllegroAuthError)


@pytest.mark.parametrize(("header", "expected"), [("30", 30.0), ("soon", None)])
async def test_429_retry_after(client, aioclient_mock, header, expected):
    aioclient_mock.get(PACKAGES_URL, status=429, headers={"Retry-After": header})
    with pytest.raises(AllegroApiError) as err:
        await client.async_get_packages()
    assert err.value.status_code == 429
    assert err.value.retry_after == expected


async def test_network_error_propagates(client, aioclient_mock):
    aioclient_mock.get(USERS_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(aiohttp.ClientError):
        await client.async_get_login()


async def test_cookie_never_in_error_text(client, aioclient_mock):
    aioclient_mock.get(USERS_URL, status=500, text=f"echo {COOKIE}")
    with pytest.raises(AllegroApiError) as err:
        await client.async_get_login()
    assert COOKIE not in str(err.value)
