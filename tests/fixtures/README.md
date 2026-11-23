# Allegro fixtures

Real responses from one buyer account, captured 2026-11-24 00:40 CET with
`scripts/capture.py` and scrubbed by it (personal data, pickup codes, pickup
points, UUIDs and waybills replaced with stable fakes; waybills keep their
length and character classes, UUIDs stay consistent across files so joins
work). Re-scrub without calling Allegro: `python3 scripts/capture.py --offline`.

## What the data shows

- `myorders.json`: 25 orders in `orderGroups[].myorders[]`, one waybill per
  order (no split shipment in this sample), one order without a waybill
  (`ORDER_CANCELLED`).
- Order status lives in `status.primary.status`: `DELIVERED` (19),
  `IN_TRANSIT` (5), `ORDER_CANCELLED` (1). `delivery.status` repeats it
  (null for the cancelled order).
- `packages.json`: 5 packages, only the not-yet-delivered ones. Each has
  `delivery.{carrierId, waybill, status, pickup.validTo, description, timer}`
  and `order.id`, which equals the order's `id` in `myorders` (join key).
- `carrierId` values seen: `ALLEGRO` (Allegro One), `GLS`.
- Carrier per order, from `delivery`:

  | `delivery.name` | `delivery.deliveredBy` | `waybills[].carrier.name` | waybill length |
  |---|---|---|---|
  | Allegro One Kurier | Delivery by Allegro One | Allegro | 10 |
  | Kurier GLS | Delivery by GLS | GLS | 11 |
  | Allegro Kurier DPD (AD) | Delivery by DPD | Allegro | 17 |
  | Allegro Automat ORLEN Paczka | Delivery by ORLEN Paczka | Allegro | 17 |

  `waybills[].carrier.name` is `Allegro` for every Allegro Delivery service,
  so it does not identify the courier; `deliveredBy` does.
- ETA: no structured field. Only text, e.g. `status.primary.hint`
  "Estimated delivery at your place to: Tue Nov 24" and
  `packages[].delivery.description.subtitle`. `timer` is null in every package.
- History: no per-package event list in either endpoint.
- Texts are English: the client sends no `Accept-Language`.

## Not yet seen

`carrierId` for DPD, InPost, ORLEN Paczka, Poczta Polska; statuses
`AVAILABLE_FOR_PICKUP`, `IN_DELIVERY`, `RETURNED`; a pickup-point package with
`pickup.validTo`; a split shipment.

## Cookie lifetime (1.0 gate)

| Check | Date | Same cookie still works? |
|---|---|---|
| Capture | 2026-11-24 00:40 CET | yes |
| +24 h | | |
| +7 days | | |
