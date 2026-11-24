"""Handing Allegro parcels over to the suite's courier integrations."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.allegro_orders.const import CONF_COOKIE, CONF_HAND_OFF, DOMAIN
from custom_components.allegro_orders.handoff import issue_id

from .payloads import ACTIVE_CODE, active_sample, delivered_sample

CLIENT = "custom_components.allegro_orders.account.client.AllegroClient"


def _courier(code: str = ACTIVE_CODE, delivered_by: str = "Delivery by DPD") -> dict:
    sample = active_sample(code)
    delivery = sample["order"]["delivery"]
    delivery["deliveredBy"] = delivered_by
    # The courier's own waybill (seller's contract), not an Allegro Delivery one.
    delivery["waybillsData"]["waybills"][0]["carrier"]["name"] = delivered_by.rsplit(
        maxsplit=1
    )[-1]
    return sample


async def test_orlen_allegro_number_never_handed_off(hass):
    """'Allegro Automat ORLEN Paczka': only Allegro can track that number."""
    calls = _register(hass, "orlen_paczka")
    sample = active_sample()
    sample["order"]["delivery"]["deliveredBy"] = "Delivery by ORLEN Paczka"
    await _setup(hass, [sample])
    assert calls == []
    assert not ir.async_get(hass).issues


async def test_dpd_allegro_number_is_handed_off(hass):
    """'Allegro Kurier DPD (AD)': the AD… number is handed to DPD as is."""
    calls = _register(hass, "dpd")
    sample = active_sample()
    sample["order"]["delivery"]["deliveredBy"] = "Delivery by DPD"
    await _setup(hass, [sample])
    assert [call["tracking_code"] for call in calls] == [ACTIVE_CODE]


def _register(hass, domain: str, *, contents: bool = True) -> list[dict]:
    """Stand in for a courier's track_parcel; returns the call log."""
    calls: list[dict] = []

    async def handler(call):
        calls.append(dict(call.data))

    fields = {vol.Required("tracking_code"): str}
    if contents:
        fields[vol.Optional("contents")] = str
    hass.services.async_register(domain, "track_parcel", handler, vol.Schema(fields))
    return calls


async def _setup(hass, parcels, **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="buyer_login",
        unique_id="buyer_login",
        data={CONF_COOKIE: "cookie-value"},
        options=options,
    )
    entry.add_to_hass(hass)
    fetch = AsyncMock(return_value=parcels)
    with (
        patch(f"{CLIENT}.async_get_login", new=AsyncMock(return_value="buyer_login")),
        patch(f"{CLIENT}.async_get_parcels", new=fetch),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, fetch


async def _refresh(hass, entry, fetch):
    with (
        patch(f"{CLIENT}.async_get_login", new=AsyncMock(return_value="buyer_login")),
        patch(f"{CLIENT}.async_get_parcels", new=fetch),
    ):
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()


async def test_dpd_parcel_handed_off_once(hass):
    calls = _register(hass, "dpd")
    entry, fetch = await _setup(hass, [_courier()])

    assert calls == [{"tracking_code": ACTIVE_CODE, "contents": "Example item"}]
    # Allegro keeps listing it; the aggregator dedupes on (carrier, barcode).
    assert [p["barcode"] for p in entry.runtime_data.coordinator.data] == [ACTIVE_CODE]

    await _refresh(hass, entry, fetch)
    assert len(calls) == 1


async def test_hand_off_survives_a_restart(hass):
    calls = _register(hass, "dpd")
    entry, fetch = await _setup(hass, [_courier()])
    with (
        patch(f"{CLIENT}.async_get_login", new=AsyncMock(return_value="buyer_login")),
        patch(f"{CLIENT}.async_get_parcels", new=fetch),
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert len(calls) == 1


async def test_contents_dropped_when_the_courier_does_not_take_them(hass):
    calls = _register(hass, "inpost", contents=False)
    await _setup(hass, [_courier(delivered_by="Delivery by InPost")])
    assert calls == [{"tracking_code": ACTIVE_CODE}]


async def test_allegro_one_never_handed_off(hass):
    calls = _register(hass, "dpd")
    await _setup(hass, [active_sample()])
    assert calls == []
    assert not ir.async_get(hass).issues


async def test_unknown_carrier_never_handed_off(hass):
    calls = _register(hass, "dpd")
    await _setup(hass, [_courier(delivered_by="Delivery by Raben")])
    assert calls == []
    assert not ir.async_get(hass).issues


async def test_delivered_parcel_not_handed_off(hass):
    calls = _register(hass, "dpd")
    sample = delivered_sample()
    sample["order"]["delivery"]["deliveredBy"] = "Delivery by DPD"
    await _setup(hass, [sample])
    assert calls == []


async def test_missing_courier_integration_raises_repair_issue(hass):
    await _setup(hass, [_courier()])
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id("dpd"))
    assert issue is not None
    assert issue.translation_placeholders["carrier"] == "DPD Polska"


async def test_courier_account_entry_without_track_parcel_raises_no_issue(hass):
    """ha-gls with only an account login lists the parcels itself, no track_parcel."""
    MockConfigEntry(domain="gls", title="myGLS").add_to_hass(hass)
    await _setup(hass, [_courier(delivered_by="Delivery by GLS")])
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("gls")) is None


async def test_issue_cleared_when_integration_installed(hass):
    entry, fetch = await _setup(hass, [_courier()])
    calls = _register(hass, "dpd")
    await _refresh(hass, entry, fetch)

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("dpd")) is None
    assert len(calls) == 1


async def test_hand_off_disabled_by_option(hass):
    calls = _register(hass, "dpd")
    await _setup(hass, [_courier()], **{CONF_HAND_OFF: False})
    assert calls == []
    assert not ir.async_get(hass).issues


async def test_courier_refusing_the_code_keeps_it_listed_and_warns(hass, caplog):
    async def refuse(call):
        raise vol.Invalid("unknown tracking code")

    hass.services.async_register("dpd", "track_parcel", refuse)
    entry, _ = await _setup(hass, [_courier()])
    assert [p["barcode"] for p in entry.runtime_data.coordinator.data] == [ACTIVE_CODE]
    assert "did not accept tracking code" in caplog.text


async def test_a_crashing_courier_service_does_not_break_the_poll(hass, caplog):
    calls = []

    async def crash(call):
        calls.append(call.data)
        raise RuntimeError("courier integration bug")

    hass.services.async_register("dpd", "track_parcel", crash)
    entry, fetch = await _setup(hass, [_courier()])
    coordinator = entry.runtime_data.coordinator
    assert coordinator.last_update_success is True
    assert [p["barcode"] for p in coordinator.data] == [ACTIVE_CODE]

    await _refresh(hass, entry, fetch)
    assert coordinator.last_update_success is True
    assert len(calls) == 1  # marked failed, not retried every poll
    assert "did not accept tracking code" in caplog.text


async def test_hand_off_waits_until_home_assistant_started(hass):
    calls = _register(hass, "dpd")
    hass.set_state(CoreState.starting)
    await _setup(hass, [_courier()])
    assert calls == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert len(calls) == 1
