"""Raw Allegro orders + packages → contract parcels."""

import copy
import json
import logging
from pathlib import Path

import pytest

from custom_components.allegro_orders.account import parcels as mapping
from custom_components.allegro_orders.account.parcels import (
    hand_off_domain,
    join_parcels,
    normalize_parcel,
)
from custom_components.allegro_orders.const import (
    ALLEGRO_CARRIERS,
    STATUS_MAP,
    ParcelStatus,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _orders() -> list[dict]:
    payload = json.loads((FIXTURES / "myorders.json").read_text())
    return [
        {**order, "groupId": group["groupId"]}
        for group in payload["orderGroups"]
        for order in group["myorders"]
    ]


def _packages() -> list[dict]:
    return json.loads((FIXTURES / "packages.json").read_text())["packages"]


def _order(delivered_by: str, status: str) -> dict:
    return copy.deepcopy(
        next(
            o
            for o in _orders()
            if o["delivery"].get("deliveredBy") == delivered_by
            and o["status"]["primary"]["status"] == status
        )
    )


def _waybill(order: dict) -> str:
    return order["delivery"]["waybillsData"]["waybills"][0]["waybillId"]


def _package_for(waybill: str, status: str = "IN_TRANSIT") -> dict:
    package = copy.deepcopy(_packages()[0])
    package["delivery"]["waybill"] = waybill
    package["delivery"]["status"] = status
    return package


def _one(orders, packages=()) -> dict:
    (parcel,) = [normalize_parcel(raw) for raw in join_parcels(orders, list(packages))]
    return parcel


@pytest.fixture(autouse=True)
def _reset_warnings():
    mapping._warned.clear()


def test_fixtures_join_to_one_parcel_per_waybill():
    parcels = [normalize_parcel(r) for r in join_parcels(_orders(), _packages())]
    # 25 orders: one cancelled, 24 with one waybill each; every package matches.
    assert len(parcels) == 24
    assert len({p["barcode"] for p in parcels}) == 24
    active = [p for p in parcels if not p["delivered"]]
    assert len(active) == 5
    assert all(p["status"] is ParcelStatus.IN_TRANSIT for p in active)


@pytest.mark.parametrize(("code", "expected"), list(STATUS_MAP.items()))
def test_status_map(code, expected):
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    parcel = _one([order], [_package_for(_waybill(order), code)])
    assert parcel["status"] is expected
    assert parcel["raw_status"] == code


def test_package_status_wins_over_order_status():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    parcel = _one([order], [_package_for(_waybill(order), "IN_DELIVERY")])
    assert parcel["status"] is ParcelStatus.OUT_FOR_DELIVERY


def test_unknown_status_is_unknown_and_warns_once(caplog):
    first = _order("Delivery by Allegro One", "IN_TRANSIT")
    second = copy.deepcopy(first)
    second["delivery"]["waybillsData"]["waybills"][0]["waybillId"] = "OTHER00001"
    packages = [
        _package_for(_waybill(first), "TELEPORTED"),
        _package_for("OTHER00001", "TELEPORTED"),
    ]
    with caplog.at_level(logging.WARNING):
        parcels = [normalize_parcel(r) for r in join_parcels([first, second], packages)]
    assert [p["status"] for p in parcels] == [ParcelStatus.UNKNOWN] * 2
    warnings = [r for r in caplog.records if "TELEPORTED" in r.getMessage()]
    assert len(warnings) == 1
    assert "github.com/uded/ha-parcels-allegro/issues" in warnings[0].getMessage()


def test_split_shipment_yields_parcel_per_waybill():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    waybills = order["delivery"]["waybillsData"]["waybills"]
    waybills.append({**waybills[0], "waybillId": "SPLIT00002"})
    parcels = [normalize_parcel(r) for r in join_parcels([order], [])]
    assert [p["barcode"] for p in parcels] == [_waybill(order), "SPLIT00002"]
    assert parcels[0]["contents"] == parcels[1]["contents"] is not None


def test_waybill_without_package_and_unmapped_order_status_is_registered():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["status"]["primary"]["status"] = "READY_FOR_PROCESSING"
    order["delivery"]["status"] = None
    parcel = _one([order])
    assert parcel["status"] is ParcelStatus.REGISTERED


def test_package_without_order_is_still_a_parcel():
    package = _package_for("LONELY0001")
    parcel = _one([], [package])
    assert parcel["barcode"] == "LONELY0001"
    assert parcel["carrier"] == "Allegro One"
    assert parcel["sender"] is None
    # The package names the item itself, so contents are not lost.
    assert parcel["contents"] == package["content"]["description"]


def test_order_without_waybill_is_not_a_parcel():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["delivery"]["waybillsData"] = {"waybills": []}
    assert join_parcels([order], []) == []


def test_cancelled_orders_are_dropped():
    cancelled = [
        o for o in _orders() if o["status"]["primary"]["status"] == "ORDER_CANCELLED"
    ]
    assert cancelled
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["cancelled"] = True
    assert join_parcels([*cancelled, order], []) == []


@pytest.mark.parametrize(
    ("delivered_by", "carrier", "domain"),
    [
        ("Delivery by Allegro One", "Allegro One", None),
        ("Delivery by DPD", "DPD Polska", "dpd"),
        ("Delivery by GLS", "GLS", "gls"),
        ("Delivery by ORLEN Paczka", "ORLEN Paczka", "orlen_paczka"),
    ],
)
def test_carrier_from_delivered_by(delivered_by, carrier, domain):
    order = copy.deepcopy(
        next(o for o in _orders() if o["delivery"].get("deliveredBy") == delivered_by)
    )
    parcel = _one([order])
    assert parcel["carrier"] == carrier
    assert hand_off_domain(parcel) == domain


def test_pocztex_is_poczta_polska():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["delivery"]["deliveredBy"] = "Delivery by Pocztex"
    parcel = _one([order])
    assert parcel["carrier"] == "Poczta Polska"
    assert hand_off_domain(parcel) == "poczta_polska"


def test_delivered_by_wins_over_package_carrier_id():
    order = _order("Delivery by DPD", "DELIVERED")
    package = _package_for(_waybill(order))  # carrierId "ALLEGRO"
    assert _one([order], [package])["carrier"] == "DPD Polska"


def test_unknown_carrier_falls_back_to_its_own_name(caplog):
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["delivery"]["deliveredBy"] = "Delivery by Raben"
    twin = copy.deepcopy(order)
    twin["delivery"]["waybillsData"]["waybills"][0]["waybillId"] = "TWIN000001"
    with caplog.at_level(logging.WARNING):
        parcels = [normalize_parcel(r) for r in join_parcels([order, twin], [])]
    assert [p["carrier"] for p in parcels] == ["Raben", "Raben"]
    assert hand_off_domain(parcels[0]) is None
    assert len([r for r in caplog.records if "Raben" in r.getMessage()]) == 1


def test_unknown_carrier_without_delivered_by_uses_delivery_name():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    del order["delivery"]["deliveredBy"]
    order["delivery"]["name"] = "Kurier Raben"
    assert _one([order])["carrier"] == "Kurier Raben"


def test_contents_lists_offers_with_quantity():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["offers"] = [
        {"title": "Kabel", "quantity": 1},
        {"title": "Ładowarka", "quantity": 3},
    ]
    assert _one([order])["contents"] == "Kabel; Ładowarka ×3"


def test_pickup_point_from_general_delivery():
    order = _order("Delivery by ORLEN Paczka", "DELIVERED")
    order["status"]["primary"]["status"] = "AVAILABLE_FOR_PICKUP"
    order["delivery"]["status"] = "AVAILABLE_FOR_PICKUP"
    parcel = _one([order])
    assert parcel["status"] is ParcelStatus.AT_PICKUP_POINT
    assert parcel["pickup"] is True
    assert parcel["pickup_point"] == order["delivery"]["generalDelivery"]["name"]


def test_courier_delivery_is_not_pickup():
    parcel = _one([_order("Delivery by Allegro One", "DELIVERED")])
    assert parcel["pickup"] is False
    assert parcel["pickup_point"] is None


def test_delivered_parcel_has_delivered_at_and_sender():
    order = _order("Delivery by Allegro One", "DELIVERED")
    parcel = _one([order])
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == order["delivery"]["timestamp"]
    assert parcel["sender"] == order["seller"]["login"]
    assert (
        parcel["url"]
        == order["delivery"]["waybillsData"]["waybills"][0]["carrier"]["url"]
    )


def test_raw_has_no_secrets():
    order = _order("Delivery by Allegro One", "IN_TRANSIT")
    order["delivery"]["waybillsData"]["waybills"][0]["pickupCode"] = {
        "code": "123456",
        "qrCode": "QRDATA",
        "receiverPhoneNumber": "+48600000000",
    }
    package = _package_for(_waybill(order))
    package["delivery"]["pickup"] = {"validTo": None, "code": "654321"}
    text = json.dumps(_one([order], [package])["raw"])
    for secret in ("123456", "QRDATA", "+48600000000", "654321"):
        assert secret not in text
    for key in ("pickupCode", "qrCode", "receiverPhoneNumber"):
        assert key not in text


def test_suite_carrier_names_match():
    # Literal `carrier` values emitted by the suite integrations; the aggregator
    # dedupes on (carrier, barcode), so these must match exactly.
    suite = {
        "dpd": "DPD Polska",  # ha-dpd custom_components/dpd/countries/pl/__init__.py:142
        "inpost": "InPost",  # ha-inpost custom_components/inpost/account/parcels.py:530
        "gls": "GLS",  # ha-gls custom_components/gls/tracking/countries/pl/__init__.py:350
        "orlen_paczka": "ORLEN Paczka",  # ha-orlen-paczka .../orlen_paczka/parcels.py:317
        "poczta_polska": "Poczta Polska",  # ha-poczta-polska .../parcels.py:309
    }
    published = {domain: name for name, domain in ALLEGRO_CARRIERS.values() if domain}
    assert published == suite
