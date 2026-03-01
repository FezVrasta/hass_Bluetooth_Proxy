# hass_Bluetooth_Proxy

A custom Home Assistant integration that turns an Android phone running the [Companion BT Proxy](https://f-droid.org/en/packages/org.kvj.habtproxy.fdroid.release/) app into a Bluetooth Low Energy scanner. BLE advertisements captured by the phone are forwarded to Home Assistant via a webhook, and the phone is registered as a BLE scanner in HA's Bluetooth stack — exactly like an ESP32 Bluetooth proxy would be.

## How it works

1. The integration creates a webhook endpoint in HA and generates a unique URL.
2. You paste that URL into the Companion BT Proxy Android app.
3. The app streams BLE advertisement data to HA over HTTP.
4. HA's Bluetooth stack receives the advertisements and makes them available to integrations such as [Bermuda BLE Trilateration](https://github.com/agittins/bermuda).

## Installation

Install via [HACS](https://hacs.xyz) by adding this repository as a custom repository, or copy the `custom_components/companion_bt_proxy` directory into your HA `config/custom_components/` folder.

## Setup

1. In HA go to **Settings → Devices & Services → Add Integration** and search for **Companion Bluetooth Proxy**.
2. Give the entry a name (e.g. the room the phone lives in) and note the generated webhook URL.
3. Open the **Companion BT Proxy** Android app and paste the webhook URL.
4. Assign the newly created HA device to a room/area.

The integration exposes a single diagnostic sensor **Last Update** that timestamps the most recent advertisement batch received from the phone.

## Android app

[Companion BT Proxy on F-Droid](https://f-droid.org/en/packages/org.kvj.habtproxy.fdroid.release/)

## Differences from upstream ([kvj/hass_Bluetooth_Proxy](https://github.com/kvj/hass_Bluetooth_Proxy))

The upstream integration registers the scanner with `source = entry_id` — a 32-character UUID string. Several parts of HA and third-party integrations assume the scanner `source` is a MAC address, which causes two problems:

### 1. Bermuda BLE Trilateration cannot use the scanner

[Bermuda](https://github.com/agittins/bermuda) calls `mac_norm()` and `mac_math_offset()` on every scanner's `source` to look up the device in the HA device registry. Applied to a UUID string these produce garbage values, the lookup returns nothing, and Bermuda raises a *"scanners without areas"* repair issue for the proxy. The scanner is never usable for distance calculations.

**Fix:** A stable, locally-administered MAC address is deterministically derived from the `entry_id` via SHA-256. The first 6 bytes of the digest are taken, the locally-administered bit is set and the multicast bit is cleared, giving a consistent `xx:xx:xx:xx:xx:xx` address that is stable across restarts without persisting any extra state.

### 2. The device entry does not merge with HA's bluetooth integration entry

Since HA 2025.2, `async_register_scanner` creates a device registry entry with `connections = {("bluetooth", source.upper())}`. The upstream `sensor.py` registered the companion device with identifier key `"entry_id"` (non-standard) instead of `DOMAIN`, and without a matching `bluetooth` connection, so the two entries never merged. This prevented area/name information from being shared between them.

**Fix:** `device_info` now uses `(DOMAIN, entry_id)` as the identifier and adds `connections = {("bluetooth", source_mac.upper())}`, allowing HA to merge the two device entries. Once you assign an area to the device, Bermuda picks it up automatically.

### 3. Bermuda shows last advertisement as ~55 years ago

The Android app includes a Unix epoch timestamp (milliseconds) with each advertisement batch. The upstream code divided this by 1000 and passed it directly as `advertisement_monotonic_time`, but HA expects a `time.monotonic()` value — seconds since machine boot, typically a small number. Passing ~1.74 billion seconds made every advertisement appear to have been received 55 years in the past, so Bermuda reported distances as stale and unusable.

**Fix:** The advertisement age is computed as `time.time() - ts_ms / 1000` and subtracted from `time.monotonic()`, correctly anchoring the phone's wall-clock timestamp to the local monotonic clock.
