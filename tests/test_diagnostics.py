"""Tests for Allegro diagnostics."""

from datetime import timedelta
from unittest.mock import MagicMock

from custom_components.allegro_orders.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_and_counts(hass):
    """Diagnostics get pasted into public issues — nothing identifying may survive."""
    entry = MagicMock()
    entry.options = {"parcels": [{"tracking_code": "EXAMPLE123456"}]}
    entry.runtime_data.coordinator.current_tier_minutes = 15
    entry.runtime_data.coordinator.update_interval = timedelta(minutes=15)
    entry.runtime_data.coordinator.data = [
        {
            "barcode": "EXAMPLE123456",
            "sender": "Example Shop",
            "receiver": "Jane Doe",
            "contents": "Running shoes",
            "status": "out_for_delivery",
            "raw": {
                "trackingNumber": "EXAMPLE123456",
                "recipient": "Jane Doe",
                "deliveryAddress": {"city": "Rotterdam", "street": "Coolsingel 1"},
            },
        }
    ]
    entry.runtime_data.coordinator.delivered = []
    entry.runtime_data.coordinator.delivered_codes = set()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["counts"] == {
        "incoming_active": 1,
        "delivered": 0,
        "skipped_from_fetch": 0,
    }
    assert result["polling"] == {
        "tier_minutes": 15,
        "update_interval_seconds": 900.0,
        "suspended": False,
    }
    # tracking codes and payload PII are redacted, at every nesting level
    assert result["entry_options"]["parcels"][0]["tracking_code"] == "**REDACTED**"
    assert result["incoming"][0]["barcode"] == "**REDACTED**"
    assert result["incoming"][0]["receiver"] == "**REDACTED**"
    assert result["incoming"][0]["contents"] == "**REDACTED**"
    assert result["incoming"][0]["raw"]["recipient"] == "**REDACTED**"
    assert result["incoming"][0]["raw"]["deliveryAddress"] == "**REDACTED**"
    # non-identifying fields survive, or the diagnostics would be useless
    assert result["incoming"][0]["status"] == "out_for_delivery"


async def test_diagnostics_redacts_cookie_and_pickup_codes(hass):
    """Allegro specifics: the cookie, pickup secrets, waybills, order ids, places."""
    entry = MagicMock()
    entry.options = {"cookie": "secret-cookie"}
    entry.runtime_data.coordinator.current_tier_minutes = 15
    entry.runtime_data.coordinator.update_interval = timedelta(minutes=15)
    entry.runtime_data.coordinator.data = [
        {
            "barcode": "W1",
            "status": "at_pickup_point",
            "pickup_point": "Paczkomat WAW01A",
            "raw": {
                "waybill": "W1",
                "order": {
                    "id": "order-uuid",
                    "group_id": "group-uuid",
                    "delivered_by": "Delivery by DPD",
                    "status": "AVAILABLE_FOR_PICKUP",
                },
                "package": {
                    "title": "Odbierz paczkę",
                    "subtitle": "Paczkomat WAW01A",
                    "code": "123456",
                    "qrCode": "QR",
                    "receiverPhoneNumber": "+48600000000",
                },
            },
        }
    ]
    entry.runtime_data.coordinator.delivered = []
    entry.runtime_data.coordinator.delivered_codes = set()

    result = await async_get_config_entry_diagnostics(hass, entry)

    text = str(result)
    for secret in (
        "secret-cookie",
        "W1",
        "order-uuid",
        "group-uuid",
        "WAW01A",
        "123456",
        "+48600000000",
    ):
        assert secret not in text, secret
    raw = result["incoming"][0]["raw"]
    assert raw["order"]["status"] == "AVAILABLE_FOR_PICKUP"
    assert raw["order"]["delivered_by"] == "Delivery by DPD"


async def test_diagnostics_reports_suspended_polling(hass):
    """update_interval None (Section 2.1's full stop) must be visible, not just absent."""
    entry = MagicMock()
    entry.options = {"parcels": []}
    entry.runtime_data.coordinator.current_tier_minutes = None
    entry.runtime_data.coordinator.update_interval = None
    entry.runtime_data.coordinator.data = []
    entry.runtime_data.coordinator.delivered = []

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["polling"] == {
        "tier_minutes": None,
        "update_interval_seconds": None,
        "suspended": True,
    }
