# Allegro — still to do

- [ ] `custom_components/allegro_orders/brand/icon.png` is still the template placeholder
- [ ] Install in a real Home Assistant and follow one real parcel through two status changes
- [ ] Cookie lifetime: re-run `scripts/capture.py` with the same cookie at +24 h and +7 days (see `tests/fixtures/README.md`); this gates 1.0
- [ ] Confirm whether DPD and ORLEN Paczka parcels sent through Allegro Delivery (17-character waybills) can be tracked by ha-dpd / ha-orlen-paczka with that number
- [ ] Capture real `carrierId`s for DPD, InPost, ORLEN Paczka, Poczta Polska and the statuses `AVAILABLE_FOR_PICKUP`, `IN_DELIVERY`, `RETURNED`
- [ ] Register `allegro_orders` with ha-parcel-aggregator (`KNOWN_CARRIERS`, `CARRIER_EVENT_PREFIXES`, `SHOP_DOMAINS`)
