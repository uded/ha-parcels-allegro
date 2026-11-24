# Allegro — still to do

- [ ] `custom_components/allegro_orders/brand/icon.png` is still the template placeholder
- [ ] Install in a real Home Assistant and follow one real parcel through two status changes
- [ ] Cookie lifetime: re-run `scripts/capture.py` with the same cookie at +24 h and +7 days (see `tests/fixtures/README.md`); this gates 1.0
- [ ] "Allegro Kurier DPD (AD)" orders show a 17-character Allegro number in myorders (`carrier.name: Allegro`), so they are not handed off. Find where the DPD number lives for those (an active parcel in `/packages`, or another endpoint) and hand that one to ha-dpd
- [ ] Capture real `carrierId`s for DPD, InPost, ORLEN Paczka, Poczta Polska and the statuses `AVAILABLE_FOR_PICKUP`, `IN_DELIVERY`, `RETURNED`
- [ ] Register `allegro_orders` with ha-parcel-aggregator (`KNOWN_CARRIERS`, `CARRIER_EVENT_PREFIXES`, `SHOP_DOMAINS`)
