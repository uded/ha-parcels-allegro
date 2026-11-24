# Allegro Parcel Tracker

[![Release](https://img.shields.io/github/v/release/uded/ha-parcels-allegro.svg)](https://github.com/uded/ha-parcels-allegro/releases)
[![Marketplace](https://img.shields.io/badge/Marketplace-Custom-41BDF5.svg)](https://hacs.xyz)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 📦 Follows the [**ha-parcel-integrations**](https://ha-parcel-integrations.github.io/) parcel contract: the same parcel format, statuses and events as the suite's couriers, so Allegro parcels plug into cross-carrier automations and the [Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator).

A custom Home Assistant integration that tracks the parcels of things you **bought** on [Allegro](https://allegro.pl). Every shipment of your recent purchases shows up automatically, with the real courier, the item name and the seller. Only parcels: no cart, messages or offers.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Options](#options)
- [Hand-off to courier integrations](#hand-off-to-courier-integrations)
- [Sensors](#sensors)
- [Parcel status reference](#parcel-status-reference)
- [Events](#events)
- [Services](#services)
- [Known limits](#known-limits)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)
- [License](#license)

## Features

- Imports every parcel of your recent Allegro purchases; no per-parcel setup
- The real courier as `carrier` (`Allegro One`, `DPD Polska`, `InPost`, `GLS`, `ORLEN Paczka`, `Poczta Polska`, …), the item names as `contents`, the seller as `sender`
- Allegro One (Box and Kurier) parcels, which no other integration covers
- Per-parcel sensor with the canonical status and Allegro's own status code, pickup point and tracking link
- Summary sensors: incoming parcels, awaiting pickup, recently delivered
- Events and device triggers for no-code automations
- Optional hand-off to the suite's courier integrations (see below)
- A `contents` field you can override with the `allegro_orders.update_contents` service

## Requirements

- Home Assistant 2025.12 or newer
- An Allegro buyer account, signed in on allegro.pl in a browser

## Installation

### Marketplace (recommended)

In the Marketplace, choose the three-dot menu → **Custom repositories**, add `https://github.com/uded/ha-parcels-allegro` as an **Integration** and install **Allegro**. Restart Home Assistant.

### Manual

Copy `custom_components/allegro_orders` into your `config/custom_components/` folder and restart Home Assistant.

## Configuration

Allegro offers no sign-in for apps and no buyer API, so the integration uses your browser session cookie, `QXLSESSID`:

1. Open [allegro.pl](https://allegro.pl) in a browser and sign in.
2. Open the developer tools (F12) → **Application** (Chrome, Edge) or **Storage** (Firefox) → **Cookies** → `https://allegro.pl`.
3. Copy the value of `QXLSESSID`.
4. In Home Assistant: **Settings → Devices & Services → Add Integration → Allegro**, paste the value.

When the cookie expires, Home Assistant asks you for a new one (a re-authentication notice); repeat the steps above. Treat the cookie like a password: it gives access to your Allegro account.

## Options

Open **Configure** on the integration entry:

| Section | Option | Default | Description |
|---|---|---|---|
| Delivered parcels | Filter by / amount | last 7 days | How long delivered parcels stay on the delivered sensor. |
| Courier integrations | Hand parcels to courier integrations | on | See below. |

Polling is automatic: no polling between 00:00 and 06:00 apart from one check at each end, every 15 minutes while a parcel is out for delivery, every 45 minutes otherwise. Each poll makes two requests to Allegro.

## Hand-off to courier integrations

Allegro knows what you bought; the courier knows where the parcel is. When a parcel travels with a courier that has its own suite integration (InPost, DPD, GLS, ORLEN Paczka, Poczta Polska), this integration calls that courier's `track_parcel` once with the waybill and, where the courier accepts it, the item name. The courier integration then adds its delivery window and history.

Example: you bought something that ships with DPD and you already run the DPD integration. Allegro lists the parcel as `carrier: DPD Polska` and hands its number to DPD, which starts tracking it too. The [Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator) shows it once: it treats Allegro as a shop and keeps the courier's record, with the item name from Allegro. The per-integration sensors still count it in both.

- **Allegro One** parcels are never handed off; Allegro is their only source.
- **Allegro Delivery numbers** (17 characters, starting `AD`): "Allegro Kurier DPD (AD)" parcels are handed to DPD with that number. "Allegro Automat ORLEN Paczka" numbers are trackable only on Allegro, so they stay here.
- If the DPD integration already lists the same parcel from your DPD account under DPD's own number, the aggregator can show it twice: nothing in Allegro's data links the two numbers yet.
- A courier without a suite integration (for example Raben) stays here only.
- If the courier's integration is not installed, a Repair issue suggests it. Turn the option off to stop hand-offs and the issue.

## Sensors

| Entity | Description |
|---|---|
| `sensor.allegro_<login>_incoming_parcels` | Number of active parcels, full list under the `parcels` attribute |
| `sensor.allegro_<login>_parcel_<code>` | One per active parcel; state is the canonical status |
| `sensor.allegro_<login>_next_delivery` | Earliest expected delivery (empty: Allegro gives no structured ETA) |
| `sensor.allegro_<login>_en_route_to_pickup_point` | Parcels on their way to a pickup point |
| `sensor.allegro_<login>_awaiting_pickup` | Parcels ready to collect |
| `sensor.allegro_<login>_delivered_parcels` | Recently delivered parcels (see the retention option) |
| `calendar.allegro_<login>_deliveries` | Calendar of expected deliveries |
| `sensor.allegro_<login>_last_successful_update` | Diagnostic: last successful poll |

## Parcel status reference

| Status | Allegro code |
|---|---|
| `registered` | a waybill exists, no live status yet |
| `in_transit` | `IN_TRANSIT` |
| `out_for_delivery` | `IN_DELIVERY` |
| `at_pickup_point` | `AVAILABLE_FOR_PICKUP` |
| `delivered` | `DELIVERED` |
| `returning` | `RETURNED`, `RETURNED_TO_SENDER` (failed delivery going back) |
| `unknown` | a code not mapped yet (logged once, please report it) |

Cancelled orders are not parcels. Allegro's own code is always in `raw_status`.

## Events

| Event | When |
|---|---|
| `allegro_orders_parcel_registered` | A new parcel appears |
| `allegro_orders_parcel_status_changed` | A parcel's canonical status changes |
| `allegro_orders_parcel_delivered` | A parcel is delivered |
| `allegro_orders_parcel_delivery_time_changed` | The delivery window changes (not fired today: no ETA source) |

Every payload is the full parcel plus the hub's `device_id`. Events are suppressed on the first refresh after start-up.

## Services

| Service | Fields | Description |
|---|---|---|
| `allegro_orders.update_contents` | `tracking_code`, `contents` | Override what is in a parcel; an empty `contents` returns to Allegro's item name. |

## Known limits

- **Undocumented API.** This uses the same endpoints allegro.pl uses in your browser. Allegro can change them at any time. An official buyer API is not planned for 2026 ([allegro/allegro-api#5394](https://github.com/allegro/allegro-api/discussions/5394)); the integration is built so that it can switch to one.
- **Cookie lifetime.** How long a `QXLSESSID` stays valid under this polling is still being measured. Until then this is a 0.x pre-release.
- **Recent orders only.** Each poll reads the latest 25 orders.
- **No delivery window, weight or history.** Allegro shows the ETA only as text.
- **Returns you send** to a seller are not tracked.

## Debugging

```yaml
logger:
  logs:
    custom_components.allegro_orders: debug
```

The cookie is never logged. Diagnostics redact it, waybills, order ids, pickup codes and pickup points.

## Troubleshooting

- **"Unrecognised Allegro status" or "Unrecognised Allegro carrier" in the log**: please [open an issue](https://github.com/uded/ha-parcels-allegro/issues/new?template=unrecognised_status.yml) with the logged line.
- **Setup says the cookie was rejected**: copy it again from a browser tab where you are signed in; make sure you copied `QXLSESSID` and not another cookie.
- **"Could not reach Allegro"**: Allegro answered with an error or a bot-protection page. The integration keeps the last data and retries.

## Disclaimer

This is an independent, community-built project. It is not affiliated with, endorsed by, sponsored by, or supported by Allegro, Home Assistant, or any other third party referenced in this project. Please don't contact Allegro for support with this integration.

All third-party trademarks, trade names, product names, logos, and other brand assets are the property of their respective owners. References to them are solely to identify the relevant service and do not imply affiliation, sponsorship, or endorsement.

This integration relies on undocumented Allegro interfaces, accessed with your own session. They may change or be withdrawn without notice and may be subject to Allegro's terms. Data is sent only to Allegro and, with hand-off on, to your own courier integrations; this project operates no servers of its own. You are responsible for ensuring that your use complies with applicable law and those terms. Use is at your own risk; see the [licence](LICENSE) for warranty limitations.

## License

[MIT](LICENSE)
