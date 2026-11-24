"""Joined Allegro samples (one per waybill), as AllegroClient.async_get_parcels returns.

Shaped like the real fixtures in tests/fixtures/, reduced to the fields the
mapping reads. Kept in one module so a payload change has one place to fix.
"""

from __future__ import annotations

ACTIVE_CODE = "EXAMPLE999999"
DELIVERED_CODE = "EXAMPLE123456"


def _order(code: str, status: str) -> dict:
    return {
        "id": f"order-{code}",
        "groupId": f"group-{code}",
        "seller": {"login": "Example Shop"},
        "offers": [{"title": "Example item", "quantity": 1}],
        "orderDate": "2026-04-27T10:00:00Z",
        "status": {"primary": {"status": status}},
        "delivery": {
            "name": "Allegro One Kurier",
            "deliveredBy": "Delivery by Allegro One",
            "status": status,
            "timestamp": "2026-04-29T13:12:42Z",
            "waybillsData": {
                "waybills": [
                    {
                        "waybillId": code,
                        "carrier": {
                            "name": "Allegro",
                            "url": "https://allegro.pl/allegrodelivery/"
                            f"sledzenie-paczki?numer={code}",
                        },
                    }
                ]
            },
        },
    }


def _package(code: str, status: str) -> dict:
    return {
        "content": {"description": "Example item"},
        "delivery": {
            "carrierId": "ALLEGRO",
            "waybill": code,
            "status": status,
            "pickup": {"validTo": None},
            "description": {"title": "Your parcel is on its way", "subtitle": None},
            "timer": None,
        },
    }


def delivered_sample(code: str = DELIVERED_CODE) -> dict:
    """A delivered parcel: only the order knows it, /packages no longer lists it."""
    return {
        "waybill": code,
        "carrier_id": None,
        "order": _order(code, "DELIVERED"),
        "package": None,
    }


def active_sample(code: str = ACTIVE_CODE, status: str = "IN_DELIVERY") -> dict:
    """An out-for-delivery parcel (live status from /packages)."""
    return {
        "waybill": code,
        "carrier_id": "ALLEGRO",
        "order": _order(code, "IN_TRANSIT"),
        "package": _package(code, status),
    }


def pickup_sample(code: str = ACTIVE_CODE) -> dict:
    """A parcel waiting at a pickup point."""
    sample = active_sample(code, "AVAILABLE_FOR_PICKUP")
    sample["order"]["delivery"]["generalDelivery"] = {
        "name": "Example Point Central Station"
    }
    return sample
