# Allegro Parcel Tracker

[![Release](https://img.shields.io/github/v/release/uded/ha-parcels-allegro.svg)](https://github.com/uded/ha-parcels-allegro/releases)
[![Downloads](https://img.shields.io/github/downloads/uded/ha-parcels-allegro/total.svg)](https://github.com/uded/ha-parcels-allegro/releases)
[![Marketplace](https://img.shields.io/badge/Marketplace-Custom-41BDF5.svg)](https://hacs.xyz)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 📦 Part of [**ha-parcel-integrations**](https://ha-parcel-integrations.github.io/), a family of package-tracking integrations for Home Assistant that all publish the same parcel format, statuses and events, so they plug into cross-carrier automations and the optional [Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator). Browse the other carriers on the website.
>
> 💬 Questions or feedback? Join the discussion on the [Home Assistant community](https://community.home-assistant.io/t/packages-postnl-dhl-nl-dpd-and-gls-parcel-integration/112433/).

<!-- TODO(carrier): rewrite this paragraph, the Requirements and the Disclaimer for the real carrier — country, what a user needs, and whether an account is involved. -->

A custom Home Assistant integration that tracks your [Allegro](https://example-carrier.test) parcels. Sign in with your own Allegro account and every parcel it already knows about is imported automatically.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Options](#options)
- [Removal](#removal)
- [Sensors](#sensors)
- [Parcel status reference](#parcel-status-reference)
- [Events](#events)
- [Services](#services)
- [Examples](#examples)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Related integrations](#related-integrations)
- [Disclaimer](#disclaimer)
- [Contributing](#contributing)
- [License](#license)

## Features

- Auto-imports every parcel your Allegro account already knows about — no per-parcel setup
- Per-parcel sensor with the canonical status (`registered` / `in_transit` / `out_for_delivery` / `delivered` / …), the carrier's own status text, the expected delivery window and a tracking deep-link
- Summary sensors: incoming parcels, next delivery, recently delivered parcels
- Read-only **Deliveries** calendar with the expected delivery windows
- `allegro_orders.track_parcel` / `allegro_orders.untrack_parcel` services, so a dashboard button can add a parcel
- A `contents` field on every parcel, set in your own words with the `allegro_orders.update_contents` service
- Events + device triggers for no-code automations (parcel registered, status changed, delivered, delivery time changed)
- Opt-in per-parcel status history
- Manual refresh button and a diagnostic last-update sensor

## Requirements

- Home Assistant 2025.12 or newer
- An Allegro account (the same one you use on the Allegro
  website or app)

## Installation

### Marketplace (recommended)

Click the button below to open this repository in the Marketplace, then install **Allegro**:

[![Open your Home Assistant instance and open a repository inside the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-parcel-integrations&repository=ha-parcels-allegro&category=integration)

Or add it by hand: in the Marketplace, choose the three-dot menu → **Custom repositories**, add `https://github.com/uded/ha-parcels-allegro` as an **Integration** and install **Allegro**.

Restart Home Assistant if it asks you to.

### Manual

Copy `custom_components/allegro_orders` into your `config/custom_components/` folder and restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=allegro_orders)

Add the integration via **Settings → Devices & Services → Add Integration → Allegro** and sign in with your Allegro account email and password.

Then add parcels via the integration's **Configure** dialog, the [`allegro_orders.track_parcel`](#services) service, or a [dashboard button](examples/dashboards/add_parcel_card.yaml). The tracking code is on your shipping confirmation email or the missed-delivery card.

## Options

Open **Configure** on the integration entry:

| Section | Option | Default | Description |
|---|---|---|---|
| Parcels | Add / remove | — | Manage the tracked tracking codes. Changes apply immediately, no restart. |
| Delivered parcels | Filter by / amount | last 7 days | How long delivered parcels stay visible on the delivered sensor. |
| Parcel history | Include status history | off | Adds a `history` attribute per parcel with each status update. |

Polling isn't one of these settings: the integration polls on a dynamic,
status-driven schedule with nothing to configure.

## Dynamic polling

Polling isn't a setting here — the integration adjusts its own cadence to
what your tracked parcels are actually doing:

- **Quiet hours** — no polling between 00:00–06:00 local time, aside from one
  catch-up check at each end of that window (around midnight and around 6
  AM), so an overnight update is never missed.
- **Hot (every 15 minutes)** — while any tracked parcel is out for delivery
  today, starting an hour before its delivery window opens (or immediately if
  no window is known yet).
- **Normal (every 45 minutes)** — for anything else still on its way.
- **Never fully stops** — with nothing hot or in transit, polling keeps
  running at the normal cadence, since that's also how a new shipment on your
  account gets discovered.
- A small, fixed per-hub offset is added on top, so not every Allegro
  hub out there polls at exactly the same second.

<!-- TODO(carrier): if this carrier's polling diverges from the schedule above (e.g. no delivery window at all, so it always falls into the hot-tier fallback), say so explicitly here — see CLAUDE.md's "Dynamic polling" section for this carrier's specifics. -->

## Removal

Standard HA removal applies: **Settings → Devices & Services → Allegro → ⋮ → Delete**. Nothing is stored on Allegro's side.

## Sensors

| Entity | Description |
|---|---|
| `sensor.allegro_orders_incoming_parcels` | Number of active tracked parcels, full list under the `parcels` attribute |
| `sensor.allegro_orders_parcel_<code>` | One per tracked parcel; state is the canonical status, attributes carry the full normalised parcel |
| `sensor.allegro_orders_next_delivery` | Earliest expected delivery moment across all active parcels |
| `sensor.allegro_orders_en_route_to_pickup_point` | Incoming parcels on their way to a pickup point that have not arrived yet |
| `sensor.allegro_orders_awaiting_pickup` | Incoming parcels that are ready to collect at a pickup point |
| `sensor.allegro_orders_delivered_parcels` | Recently delivered parcels (see the retention option) |
| `calendar.allegro_orders_deliveries` | Read-only calendar of expected deliveries, no extra API calls |
| `sensor.allegro_orders_last_successful_update` | Diagnostic: when Allegro was last polled successfully |

A delivered parcel moves from its per-parcel sensor to the delivered sensor automatically.

## Parcel status reference

The `status` field is the carrier-agnostic enum shared by the whole integration family:

<!-- TODO(carrier): trim this table to the statuses this carrier can actually
     report — listing states that never occur just confuses users. -->

| Status | Meaning |
|---|---|
| `registered` | Announced / received by Allegro |
| `in_transit` | In the sorting network |
| `out_for_delivery` | With the courier today |
| `at_pickup_point` | Waiting for you at a pickup location |
| `delivered` | Delivered |
| `returning` | Going back to the sender |
| `problem` | Allegro reports an exception |
| `unknown` | Not yet scanned, or a status we have not mapped yet |

The carrier's own human-readable text is always available as `raw_status`.

## Events

The integration fires these on the event bus (also available as device triggers on the Allegro device):

| Event | When |
|---|---|
| `allegro_orders_parcel_registered` | A new parcel appears in the active list |
| `allegro_orders_parcel_status_changed` | A parcel's canonical status changes (`old_status` / `new_status` in the payload), except the final hop to delivered |
| `allegro_orders_parcel_delivered` | A parcel is delivered |
| `allegro_orders_parcel_delivery_time_changed` | The expected delivery window changes |

Every payload is the full normalised parcel plus the hub's `device_id`. Events are suppressed on the first refresh after start-up.

## Services

| Service | Fields | Description |
|---|---|---|
| `allegro_orders.track_parcel` | `tracking_code`, `contents` (optional) | Start tracking a parcel, optionally noting what is in it |
| `allegro_orders.untrack_parcel` | `tracking_code` | Stop tracking a parcel |
| `allegro_orders.update_contents` | `tracking_code`, `contents` | Set what is in a parcel, tracked or not; an empty `contents` clears it. With several accounts it goes to every account that lists the code; name one with the optional `config_entry_id` (needed for a code no account lists yet) |

## Examples

Ready-to-paste automations and dashboard snippets live in [`examples/`](examples/), including tracking a new parcel straight from a dashboard.

### Community Lovelace cards

Third-party cards that work with this integration's sensors:

- [jonisnet/ha-parcel-card](https://github.com/jonisnet/ha-parcel-card)
- [klaptafel/ha-package-tracker-card](https://github.com/klaptafel/ha-package-tracker-card)

## Debugging

```yaml
logger:
  logs:
    custom_components.allegro_orders: debug
```

## Troubleshooting

- **A parcel shows `unknown`** — Allegro has not scanned it yet (their API answers `not_found` until the first scan), or the code is wrong. It will pick up automatically once scanned.
- **A status logs "Unrecognised Allegro status"** — please [open an issue](https://github.com/uded/ha-parcels-allegro/issues/new?template=unrecognised_status.yml) with the logged line so the mapping can be extended.

## Related integrations

This integration is part of [**ha-parcel-integrations**](https://ha-parcel-integrations.github.io/) — a family of
parcel-carrier integrations that all publish the same canonical parcel format,
statuses and events.

- [**Parcel Aggregator**](https://github.com/ha-parcel-integrations/ha-parcel-aggregator) rolls every installed carrier
  up into one set of sensors.
- Browse [the organisation](https://ha-parcel-integrations.github.io/) for the current list of supported carriers.

## Disclaimer

This is an independent, community-built project. It is not affiliated with, endorsed by, sponsored by, or supported by Allegro, Home Assistant, or any other third party referenced in this project. Please don't contact Allegro for support with this integration.

All third-party trademarks, trade names, product names, logos, and other brand assets are the property of their respective owners. References to them are solely to identify the relevant carrier or service and do not imply affiliation, sponsorship, or endorsement. Nothing in this project grants or implies any licence or right to use third-party brand assets.

This integration may rely on public, unofficial, or undocumented carrier interfaces, accessed with your own account or API key where required. These may change or be withdrawn without notice and may be subject to Allegro's terms. Data is sent only to Allegro's own services or those of its group; this project operates no servers of its own. You are responsible for ensuring that your use complies with applicable law and those terms. Use is at your own risk; see the [licence](LICENSE) for warranty limitations.

This integration uses the same public tracking endpoint as the Allegro consumer website.

## Contributing

Pull requests and issues are welcome. Please open an issue before
submitting a large change.

## License

[MIT](LICENSE)
