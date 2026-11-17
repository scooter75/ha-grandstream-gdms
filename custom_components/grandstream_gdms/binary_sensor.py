"""Binary sensor platform for Grandstream GDMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GdmsDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GDMS binary sensors from a config entry."""
    coordinator: GdmsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices: dict[str, dict[str, Any]] = coordinator.data.get("devices", {})

    entities: list[BinarySensorEntity] = [
        GdmsDeviceConnectivitySensor(coordinator, mac) for mac in devices
    ]
    async_add_entities(entities)


class GdmsDeviceConnectivitySensor(
    CoordinatorEntity[GdmsDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a GDMS device is online."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Status"

    def __init__(self, coordinator: GdmsDataUpdateCoordinator, mac: str) -> None:
        """Initialize the connectivity binary sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_connectivity"

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("devices", {}).get(self._mac, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._device_data)

    @property
    def is_on(self) -> bool:
        return bool(self._device_data.get("is_online", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dev = self._device_data
        return {
            "mac_address": self._mac,
            "serial_number": dev.get("sn"),
            "model": dev.get("deviceType") or dev.get("model"),
            "firmware_version": dev.get("firmwareVersion") or dev.get("version"),
            "local_ip": dev.get("ip") or dev.get("privateIp"),
            "public_ip": dev.get("publicIp"),
            "site_name": dev.get("site_name"),
            "last_online_time": dev.get("lastOnlineTime"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        dev = self._device_data
        device_name = dev.get("deviceName") or f"Grandstream {self._mac}"
        model = dev.get("deviceType") or dev.get("model") or "Grandstream Device"
        sw_version = dev.get("firmwareVersion") or dev.get("version")
        serial_number = dev.get("sn")

        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            name=device_name,
            manufacturer="Grandstream Networks",
            model=model,
            sw_version=sw_version,
            serial_number=serial_number,
            suggested_area=dev.get("site_name"),
        )
