from __future__ import annotations
from .constants import CONF_ADDRESS_FILTER, DOMAIN, PLATFORMS
from .scanner import CompanionBLEScanner

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import webhook

import voluptuous as vol
import logging
import re

from aiohttp.web import json_response

_LOGGER = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


def parse_address_filter(raw: str | None) -> set[str]:
    """Parse the address allow-list option into a set of upper-case addresses.

    Accepts addresses separated by commas, semicolons or whitespace. Entries
    that are not valid MAC addresses are skipped with a warning rather than
    silently discarding the whole filter. An empty option yields an empty set,
    which callers treat as "accept everything".
    """
    if not raw:
        return set()
    allowed: set[str] = set()
    invalid: list[str] = []
    for part in re.split(r"[,;\s]+", raw):
        candidate = part.strip().upper()
        if not candidate:
            continue
        if _ADDRESS_RE.match(candidate):
            allowed.add(candidate)
        else:
            invalid.append(part.strip())
    if invalid:
        _LOGGER.warning("Ignoring malformed addresses in filter: %s", invalid)
    return allowed

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
    }, extra=vol.ALLOW_EXTRA),
}, extra=vol.ALLOW_EXTRA)

async def _async_handle_webhook(hass, webhook_id, request):
    try:
        message = await request.json()
    except ValueError:
        _LOGGER.warning(f"Invalid JSON in Webhook")
        return json_response([])
    _LOGGER.debug(f"JSON: {message}")
    entry_id = hass.data[DOMAIN]["webhooks"].get(webhook_id)
    if scanner := hass.data[DOMAIN]["scanners"].get(entry_id):
        allowed = hass.data[DOMAIN]["filters"].get(entry_id)
        if allowed:
            total = len(message)
            message = [i for i in message if str(i.get("address", "")).upper() in allowed]
            if len(message) != total:
                _LOGGER.debug("Filtered %d of %d advertisements", total - len(message), total)
        for item in message:
            await scanner.async_process_json(item)
        await scanner.async_update_sensors()
    else:
        _LOGGER.warning(f"No scanner registered for webhook {webhook_id}")
    return json_response([])

async def async_setup_entry(hass: HomeAssistant, entry):
    data = entry.as_dict()["data"]
    hook_id = data["webhook"]
    hass.data[DOMAIN]["webhooks"][hook_id] = entry.entry_id
    scanner = CompanionBLEScanner(hass, entry)
    await scanner.async_load(hass)
    entry.runtime_data = scanner
    hass.data[DOMAIN]["scanners"][entry.entry_id] = scanner
    hass.data[DOMAIN]["filters"][entry.entry_id] = parse_address_filter(
        entry.options.get(CONF_ADDRESS_FILTER)
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    webhook.async_register(hass, DOMAIN, "Companion BT Proxy", hook_id, _async_handle_webhook)
    _LOGGER.debug(f"async_setup_entry() Webhook: {hook_id}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    scanner = entry.runtime_data
    data = entry.as_dict()["data"]
    hook_id = data["webhook"]
    webhook.async_unregister(hass, hook_id)

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    hass.data[DOMAIN]["webhooks"].pop(hook_id)
    await scanner.async_unload(hass)
    hass.data[DOMAIN]["scanners"].pop(entry.entry_id)
    hass.data[DOMAIN]["filters"].pop(entry.entry_id, None)
    entry.runtime_data = None
    return True

async def _async_options_updated(hass: HomeAssistant, entry) -> None:
    """Re-read the options so filter changes apply without a restart."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data[DOMAIN] = {"scanners": {}, "webhooks": {}, "filters": {}}
    return True
