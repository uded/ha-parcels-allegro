"""The parcel contract's checks, run over every parcel built from the fixtures."""

import copy
import json
from pathlib import Path

import pytest

from custom_components.allegro_orders.account.parcels import (
    join_parcels,
    normalize_parcel,
)
from custom_components.allegro_orders.const import (
    CAPABILITIES,
    PENDING_CAPABILITIES,
    ParcelStatus,
)
from custom_components.allegro_orders.parcels import parse_iso

FIXTURES = Path(__file__).parent / "fixtures"

CANONICAL_KEYS = [
    "carrier",
    "barcode",
    "sender",
    "receiver",
    "contents",
    "status",
    "raw_status",
    "delivered",
    "delivered_at",
    "planned_from",
    "planned_to",
    "pickup",
    "pickup_point",
    "url",
    "weight",
    "dimensions",
    "history",
    "raw",
]


def _orders() -> list[dict]:
    payload = json.loads((FIXTURES / "myorders.json").read_text())
    return [
        {**order, "groupId": group["groupId"]}
        for group in payload["orderGroups"]
        for order in group["myorders"]
    ]


def _packages() -> list[dict]:
    return json.loads((FIXTURES / "packages.json").read_text())["packages"]


def _pickup_order(status: str) -> dict:
    order = copy.deepcopy(
        next(o for o in _orders() if o["delivery"].get("generalDelivery"))
    )
    order["status"]["primary"]["status"] = status
    order["delivery"]["status"] = status
    return order


def _variants() -> list[dict]:
    returned = copy.deepcopy(_orders()[0])
    returned["status"]["primary"]["status"] = "RETURNED_TO_SENDER"
    returned["delivery"]["status"] = "RETURNED_TO_SENDER"
    return [
        _pickup_order("AVAILABLE_FOR_PICKUP"),
        _pickup_order("DELIVERED"),
        returned,
    ]


ALL = [
    normalize_parcel(raw)
    for raw in join_parcels(_orders(), _packages()) + join_parcels(_variants(), [])
]


@pytest.fixture(params=range(len(ALL)))
def parcel(request) -> dict:
    return ALL[request.param]


def test_keys_and_order(parcel):
    assert list(parcel) == CANONICAL_KEYS


def test_status_is_canonical(parcel):
    assert isinstance(parcel["status"], ParcelStatus)


def test_delivered_follows_status(parcel):
    assert parcel["delivered"] is (parcel["status"] is ParcelStatus.DELIVERED)


def test_delivered_at_only_when_delivered(parcel):
    if not parcel["delivered"]:
        assert parcel["delivered_at"] is None
    else:
        assert parse_iso(parcel["delivered_at"]) is not None


def test_planned_is_empty_when_the_parcel_is_done_or_waiting(parcel):
    if parcel["status"] in (
        ParcelStatus.DELIVERED,
        ParcelStatus.AT_PICKUP_POINT,
        ParcelStatus.RETURNING,
    ):
        assert parcel["planned_from"] is None
        assert parcel["planned_to"] is None


def test_pickup_is_a_bool_and_the_point_needs_it(parcel):
    assert isinstance(parcel["pickup"], bool)
    if not parcel["pickup"]:
        assert parcel["pickup_point"] is None


def test_unexposed_fields_are_none(parcel):
    for key in ("receiver", "weight", "dimensions", "history"):
        assert parcel[key] is None


def test_a_collected_pickup_parcel_stays_pickup():
    collected = normalize_parcel(join_parcels([_pickup_order("DELIVERED")], [])[0])
    assert collected["delivered"] is True
    assert collected["pickup"] is True
    assert collected["pickup_point"]


FIELDS = {
    "pickup_point": ("pickup_point",),
    "url": ("url",),
    "contents": ("contents",),
    "delivery_window": ("planned_from", "planned_to"),
    "weight": ("weight",),
    "dimensions": ("dimensions",),
    "history": ("history",),
}


def test_capabilities_match_what_the_parcels_carry():
    """Declared capabilities come true somewhere; everything else stays None."""
    for capability, keys in FIELDS.items():
        filled = any(p[key] is not None for p in ALL for key in keys)
        assert filled is (capability in CAPABILITIES), capability
    assert not CAPABILITIES & PENDING_CAPABILITIES


def test_fixtures_cover_every_variant():
    statuses = {p["status"] for p in ALL}
    assert {
        ParcelStatus.DELIVERED,
        ParcelStatus.IN_TRANSIT,
        ParcelStatus.AT_PICKUP_POINT,
        ParcelStatus.RETURNING,
    } <= statuses
