from homeassistant.components import bluetooth

import hashlib
import logging
import base64

_LOGGER = logging.getLogger(__name__)


def _entry_id_to_mac(entry_id: str) -> str:
    """Derive a stable locally-administered MAC address from a config entry ID."""
    digest = hashlib.sha256(entry_id.encode()).digest()
    octets = bytearray(digest[:6])
    octets[0] = (octets[0] | 0x02) & 0xFE  # locally-administered, unicast
    return ":".join(f"{b:02x}" for b in octets)


class CompanionBLEScanner(bluetooth.BaseHaRemoteScanner):

    def __init__(self, hass, entry):
        self._source_mac = _entry_id_to_mac(entry.entry_id)
        self._connector = bluetooth.HaBluetoothConnector(client=None, source=self._source_mac, can_connect=lambda: False)
        super().__init__(self._source_mac, entry.title, self._connector, False)
        self._sensors = []

    async def async_process_json(self, data: dict):
        service_data = {key: base64.b64decode(value) for (key, value) in data.get("service_data", {}).items()}
        m_data = {int(key, 10): base64.b64decode(value) for (key, value) in data.get("manufacturer_data", {}).items()}
        _LOGGER.debug(f"async_process_json: {data}, {service_data}, {m_data}")
        self._async_on_advertisement(
            address=data["address"],
            rssi=data.get("rssi", 0),
            local_name=data.get("name"),
            service_uuids=data.get("service_uuids", []),
            service_data=service_data,
            manufacturer_data=m_data,
            tx_power=data.get("tx_power", 0),
            details=dict(),
            advertisement_monotonic_time=data.get("timestamp", 0) / 1000, # Milliseconds to fractional seconds
        )

    async def async_update_sensors(self):
        for s in self._sensors:
            await s.async_on_scanner_update(self)

    async def async_load(self, hass):
        self._unload_callback = bluetooth.async_register_scanner(hass, self, False)

    async def async_unload(self, hass):
        self._unload_callback()
        self._sensors = []