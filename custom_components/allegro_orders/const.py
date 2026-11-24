"""Constants for the Allegro parcel tracker integration."""

from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "allegro_orders"


class ParcelStatus(StrEnum):
    """Carrier-agnostic parcel status.

    **Do not extend or rename these members.** Every integration in the parcel
    suite publishes exactly this vocabulary on the ``status`` field of each
    normalised parcel, so cross-carrier automations and the aggregator can
    target ``status: out_for_delivery`` regardless of carrier. Listed in
    roughly the order a parcel moves through.
    """

    REGISTERED = "registered"  # Sender announced the parcel; not handed over yet
    IN_TRANSIT = "in_transit"  # In the carrier's network
    OUT_FOR_DELIVERY = "out_for_delivery"  # On a delivery vehicle today
    AT_PICKUP_POINT = "at_pickup_point"  # Ready to collect at a pickup location
    DELIVERED = "delivered"  # Handed over
    RETURNING = "returning"  # Failed delivery, going back to sender
    PROBLEM = "problem"  # Carrier reports an exception/issue
    UNKNOWN = "unknown"  # Raw status we have not mapped yet


PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]

# Allegro delivery status (package `delivery.status`, else order
# `status.primary.status`) → canonical status. ORDER_CANCELLED is not here:
# cancelled orders are not parcels at all.
STATUS_MAP: dict[str, ParcelStatus] = {
    "IN_TRANSIT": ParcelStatus.IN_TRANSIT,
    "IN_DELIVERY": ParcelStatus.OUT_FOR_DELIVERY,
    "AVAILABLE_FOR_PICKUP": ParcelStatus.AT_PICKUP_POINT,
    "DELIVERED": ParcelStatus.DELIVERED,
    "RETURNED": ParcelStatus.RETURNING,
    "RETURNED_TO_SENDER": ParcelStatus.RETURNING,
}

# Courier key → (`carrier` as the suite integration publishes it, that
# integration's domain or None). Keys are Allegro `/packages` carrierIds; only
# ALLEGRO and GLS are confirmed from real data. The `carrier` strings must match
# the suite exactly: the aggregator dedupes on (carrier, barcode).
ALLEGRO_CARRIERS: dict[str, tuple[str, str | None]] = {
    "ALLEGRO": ("Allegro One", None),
    "DPD": ("DPD Polska", "dpd"),
    "GLS": ("GLS", "gls"),
    "INPOST": ("InPost", "inpost"),
    "ORLEN": ("ORLEN Paczka", "orlen_paczka"),
    "POCZTA_POLSKA": ("Poczta Polska", "poczta_polska"),
}

# Suite domains whose track_parcel takes an Allegro Delivery number (the
# 17-character "AD…" waybill of e.g. "Allegro Kurier DPD (AD)"). ORLEN Paczka's
# Allegro numbers are trackable only on Allegro, so it is not here.
ACCEPTS_ALLEGRO_NUMBERS: frozenset[str] = frozenset({"dpd"})

# Courier named in an order's `delivery.deliveredBy` ("Delivery by DPD") →
# ALLEGRO_CARRIERS key. Preferred over carrierId, which may say ALLEGRO for any
# courier Allegro Delivery contracts (e.g. "Allegro Kurier DPD (AD)").
DELIVERED_BY: dict[str, str] = {
    "Allegro One": "ALLEGRO",
    "DPD": "DPD",
    "GLS": "GLS",
    "InPost": "INPOST",
    "ORLEN Paczka": "ORLEN",
    "Poczta Polska": "POCZTA_POLSKA",
    # Poczta Polska's courier brand.
    "Pocztex": "POCZTA_POLSKA",
}

# Every optional key the parcel contract defines. CAPABILITIES below must be a
# subset of this — it exists so a typo in CAPABILITIES fails a test instead of
# silently dropping a carrier off a table on the docs site.
KNOWN_CAPABILITIES = frozenset(
    {
        "weight",
        "dimensions",
        "delivery_window",
        "pickup_point",
        "url",
        "history",
        "contents",
    }
)

# What Allegro's data actually fills (checked by tests/test_contract.py).
# Every value not listed here comes back as a literal ``None`` from
# account/parcels.py normalize_parcel(); Allegro has no event history, weight
# or dimensions. The docs site's carrier comparison table is generated straight from
# this constant, so drift here does not stay a local mistake, it becomes a
# wrong claim on the website.
#
#   "weight"           parcel["weight"] is ever non-null
#   "dimensions"        parcel["dimensions"] is ever non-null
#   "delivery_window"   parcel["planned_from"] and/or ["planned_to"] is ever non-null
#   "pickup_point"       parcel["pickup_point"] is ever non-null (beyond the "pickup" bool)
#   "url"                parcel["url"] is ever non-null
#   "history"            the include_history option is implemented and does something
#   "contents"           parcel["contents"] is ever filled by the carrier (user-supplied text does not count)
CAPABILITIES = frozenset({"pickup_point", "url", "contents"})

# Fields whose support is not confirmed yet — typically a carrier built without
# a real parcel to check against. Leave this empty once the open questions are
# answered. A field is in exactly one of three states: in CAPABILITIES (seen
# populated), in PENDING_CAPABILITIES (docs site shows "awaiting data"), or in
# neither (the API never exposes it). Pending fields must still come back as a
# literal ``None`` from normalize_parcel() until they are confirmed and moved
# into CAPABILITIES. A multi-backend carrier declares
# PENDING_CAPABILITIES_BY_VARIANT with the same keys as its
# CAPABILITIES_BY_VARIANT instead (omit backends with nothing pending).
# Allegro shows the ETA only as text ("Estimated delivery to: Tue Nov 24").
PENDING_CAPABILITIES: frozenset[str] = frozenset({"delivery_window"})

# If this carrier ever grows a second backend with a genuinely different
# payload shape (a country-specific API, not just a config option), replace
# the single CAPABILITIES above with a CAPABILITIES_BY_VARIANT dict instead:
#
#   CAPABILITIES_BY_VARIANT = {
#       "Germany": frozenset({"pickup_point", "url", "history"}),
#       "Other": frozenset({"weight", "dimensions", "delivery_window",
#                            "pickup_point", "url", "history"}),
#   }
#
# Key order is display order on the docs site's comparison table; label each
# key exactly as the carrier's own country/backend selector does. The docs
# site's generator accepts either shape — don't declare both. Do not add this
# preemptively: a single-backend carrier (the common case) keeps the flat
# CAPABILITIES above.

# Auth: the QXLSESSID session cookie of allegro.pl, pasted by the user. It is
# sent as a Cookie header to the undocumented buyer endpoints in
# account/client.py; 401/403 or a 302 to the login page means it expired.
CONF_COOKIE = "cookie"

# Hand parcels of couriers with their own suite integration over to it
# (`<domain>.track_parcel`), like ha-amazon. On by default.
CONF_HAND_OFF = "hand_off"
DEFAULT_HAND_OFF = True

# Delivered-parcels retention: keep delivered parcels visible for the last N
# days, or keep only the N most recent — identical across the suite.
CONF_DELIVERED_FILTER_TYPE = "delivered_filter_type"
CONF_DELIVERED_FILTER_AMOUNT = "delivered_filter_amount"
DEFAULT_DELIVERED_FILTER_TYPE = "days"
DEFAULT_DELIVERED_FILTER_AMOUNT = 7

# Dynamic, status-driven polling — unconditional across the suite, no
# user-facing interval option (see CLAUDE.md's "Dynamic polling"
# section for the full algorithm and the reasoning behind it).
#
# Quiet window: no polling between these local hours except the two anchors
# below, for overnight / end-of-day catch-up.
QUIET_WINDOW_START_HOUR = 0
QUIET_WINDOW_END_HOUR = 6

# Cadence while polling is active (minutes). Hot = at least one active parcel
# is out_for_delivery within HOT_LOOKAHEAD_HOURS of its planned_from (or has
# no planned_from at all); mid = anything else still in flight. Unlike the
# barcode-based model, the account-based coordinator never fully stops — the
# mid-tier poll is also how a new shipment gets discovered.
HOT_INTERVAL_MINUTES = 15
MID_INTERVAL_MINUTES = 45
HOT_LOOKAHEAD_HOURS = 1

# Small, stable per-install offset added to every computed interval so
# different installs don't all hit an anchor or tier boundary at the same
# second. Deterministic (hash of the config entry id), not random.
STAGGER_MINUTES = 7

# The user-set parcel contents, and the tracking code the contents action is keyed on.
CONF_CONTENTS = "contents"
CONF_TRACKING_CODE = "tracking_code"
CONF_CONFIG_ENTRY_ID = "config_entry_id"
