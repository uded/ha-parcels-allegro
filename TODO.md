# Allegro — still to do

- [ ] `custom_components/allegro_orders/brand/icon.png` is still the template placeholder
- [ ] Install in a real Home Assistant and follow one real parcel through two status changes
- [ ] Cookie lifetime: re-run `scripts/capture.py` with the same cookie at +24 h and +7 days (see `tests/fixtures/README.md`); this gates 1.0
- [ ] "Allegro Kurier DPD (AD)": the `AD…` number is handed to ha-dpd. Check in a real HA that DPD accepts it. Then, with one such parcel in transit, re-run the capture and look for DPD's own number (in `/packages` or the order page) to link it with ha-dpd's account-listed copy so the aggregator dedupes it
- [ ] Capture real `carrierId`s for DPD, InPost, ORLEN Paczka, Poczta Polska and the statuses `AVAILABLE_FOR_PICKUP`, `IN_DELIVERY`, `RETURNED`
- [ ] Register `allegro_orders` with ha-parcel-aggregator (`KNOWN_CARRIERS`, `CARRIER_EVENT_PREFIXES`, `SHOP_DOMAINS`)
