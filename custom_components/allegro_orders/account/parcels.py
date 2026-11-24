"""Allegro orders + packages → contract parcels.

``myorders`` knows what was bought, from whom and by which courier; ``/packages``
knows the live status of the not-yet-delivered ones. One parcel per waybill.
"""

from __future__ import annotations

import logging
from typing import Any

from ..const import ALLEGRO_CARRIERS, DELIVERED_BY, STATUS_MAP, ParcelStatus
from ..contents import clean_contents, join_contents
from ..parcels import NEW_ISSUE_URL, is_pickup

_LOGGER = logging.getLogger(__name__)

_DOMAIN_BY_CARRIER = dict(ALLEGRO_CARRIERS.values())

# (kind, code) pairs already warned about, so each is logged once per run.
_warned: set[tuple[str, str]] = set()


def _warn_once(kind: str, code: str) -> None:
    if (kind, code) in _warned:
        return
    _warned.add((kind, code))
    _LOGGER.warning(
        "Unrecognised Allegro %s — help us map it. Open an issue and paste "
        "this line: %s\n  %s=%s",
        kind,
        NEW_ISSUE_URL,
        kind,
        code,
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _waybills(order: dict[str, Any]) -> list[dict[str, Any]]:
    data = _dict(_dict(order.get("delivery")).get("waybillsData"))
    return [w for w in data.get("waybills") or [] if isinstance(w, dict)]


def _is_cancelled(order: dict[str, Any]) -> bool:
    status = _dict(_dict(order.get("status")).get("primary")).get("status")
    return bool(order.get("cancelled")) or status == "ORDER_CANCELLED"


def join_parcels(
    orders: list[dict[str, Any]], packages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair each waybill with its order and package; cancelled orders drop out."""
    by_waybill = {
        waybill: package
        for package in packages
        if (waybill := _dict(package.get("delivery")).get("waybill"))
    }
    joined = []
    for order in orders:
        if _is_cancelled(order):
            continue
        for entry in _waybills(order):
            waybill = entry.get("waybillId")
            if not waybill:
                continue
            package = by_waybill.pop(waybill, None)
            joined.append(_raw(waybill, order, package))
    # Packages no order explains (older than the order page) are still parcels.
    joined.extend(
        _raw(waybill, None, package) for waybill, package in by_waybill.items()
    )
    return joined


def _raw(waybill: str, order: dict | None, package: dict | None) -> dict[str, Any]:
    carrier_id = _dict(_dict(package).get("delivery")).get("carrierId")
    return {
        "waybill": waybill,
        "carrier_id": carrier_id,
        "order": order,
        "package": package,
    }


def _carrier(raw: dict[str, Any]) -> str:
    delivery = _dict(_dict(raw["order"]).get("delivery"))
    delivered_by = delivery.get("deliveredBy") or ""
    key = next(
        (k for courier, k in DELIVERED_BY.items() if delivered_by.endswith(courier)),
        None,
    )
    if key is None and not delivered_by and raw["carrier_id"] in ALLEGRO_CARRIERS:
        key = raw["carrier_id"]
    if key is not None:
        return ALLEGRO_CARRIERS[key][0]
    if " by " in delivered_by:
        name = delivered_by.split(" by ", 1)[1]
    else:
        name = delivered_by or delivery.get("name") or raw["carrier_id"] or "Allegro"
    _warn_once("carrier", name)
    return name


def hand_off_domain(parcel: dict[str, Any]) -> str | None:
    """Domain of the suite integration that can track this parcel's number, if any.

    Allegro Delivery waybills (e.g. "Allegro Automat ORLEN Paczka") are
    Allegro's own numbers that only Allegro can track; never hand those off.
    """
    if _dict(parcel.get("raw")).get("allegro_number"):
        return None
    return _DOMAIN_BY_CARRIER.get(parcel.get("carrier") or "")


def _status(raw: dict[str, Any]) -> tuple[ParcelStatus, str | None]:
    package = _dict(raw["package"])
    code = _dict(package.get("delivery")).get("status") or _dict(
        _dict(_dict(raw["order"]).get("status")).get("primary")
    ).get("status")
    status = STATUS_MAP.get(code) if code else None
    if status is not None:
        return status, code
    if code:
        _warn_once("status", code)
    # Without a live package the waybill only proves the parcel was announced.
    return (ParcelStatus.UNKNOWN if package else ParcelStatus.REGISTERED), code


def _contents(order: dict[str, Any], package: dict[str, Any]) -> str | None:
    items = []
    for offer in order.get("offers") or []:
        title = clean_contents(_dict(offer).get("title"))
        quantity = _dict(offer).get("quantity") or 1
        if title:
            items.append(f"{title} ×{quantity}" if quantity > 1 else title)
    return join_contents(items) or clean_contents(
        _dict(package.get("content")).get("description")
    )


def _lean(order: dict[str, Any], package: dict[str, Any], waybill: str) -> dict:
    """The parts of the payload worth keeping, never pickup codes or QR data."""
    delivery = _dict(order.get("delivery"))
    package_delivery = _dict(package.get("delivery"))
    raw: dict[str, Any] = {"waybill": waybill}
    if order:
        raw["order"] = {
            "id": order.get("id"),
            "group_id": order.get("groupId"),
            "order_date": order.get("orderDate"),
            "status": _dict(_dict(order.get("status")).get("primary")).get("status"),
            "delivery_method": delivery.get("name"),
            "delivered_by": delivery.get("deliveredBy"),
            "delivery_status": delivery.get("status"),
            "status_changed": delivery.get("timestamp"),
        }
    if package:
        raw["package"] = {
            "carrier_id": package_delivery.get("carrierId"),
            "status": package_delivery.get("status"),
            "title": _dict(package_delivery.get("description")).get("title"),
            "subtitle": _dict(package_delivery.get("description")).get("subtitle"),
            "pickup_valid_to": _dict(package_delivery.get("pickup")).get("validTo"),
        }
    return raw


def normalize_parcel(raw: dict[str, Any], *, include_history: bool = False) -> dict:
    """Return the contract parcel for one joined waybill.

    ``include_history`` is accepted for the coordinator's signature; Allegro
    exposes no event history, so ``history`` is always ``None``.
    """
    order = _dict(raw["order"])
    package = _dict(raw["package"])
    waybill = raw["waybill"]
    delivery = _dict(order.get("delivery"))
    status, code = _status(raw)
    delivered = status is ParcelStatus.DELIVERED
    point = _dict(delivery.get("generalDelivery"))
    pickup = is_pickup(bool(point), status)
    entry = next((w for w in _waybills(order) if w.get("waybillId") == waybill), {})

    return {
        "carrier": _carrier(raw),
        "barcode": waybill,
        "sender": _dict(order.get("seller")).get("login") or None,
        "receiver": None,
        "contents": _contents(order, package),
        "status": status,
        "raw_status": code,
        "delivered": delivered,
        "delivered_at": delivery.get("timestamp") if delivered else None,
        "planned_from": None,
        "planned_to": None,
        "pickup": pickup,
        "pickup_point": (point.get("name") or None) if pickup else None,
        "url": _dict(entry.get("carrier")).get("url") or None,
        "weight": None,
        "dimensions": None,
        "history": None,
        "raw": {
            **_lean(order, package, waybill),
            # The waybill's issuer: "Allegro" means Allegro's own tracking number.
            "allegro_number": (
                _dict(entry.get("carrier")).get("name") == "Allegro"
                if entry
                else raw["carrier_id"] == "ALLEGRO"
            ),
        },
    }
