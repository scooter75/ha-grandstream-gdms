"""Sensor platform for Grandstream GDMS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GdmsDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class GdmsDeviceSensorDescription(SensorEntityDescription):
    """Describe a GDMS per-device sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


DEVICE_SENSORS: tuple[GdmsDeviceSensorDescription, ...] = (
    GdmsDeviceSensorDescription(
        key="ip_address",
        name="IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("ip") or d.get("privateIp"),
    ),
    GdmsDeviceSensorDescription(
        key="public_ip",
        name="Public IP",
        icon="mdi:earth",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("publicIp"),
    ),
    GdmsDeviceSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmwareVersion") or d.get("version"),
    ),
    GdmsDeviceSensorDescription(
        key="site_name",
        name="Site",
        icon="mdi:office-building-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("site_name"),
    ),
    GdmsDeviceSensorDescription(
        key="sip_registration",
        name="SIP Registration",
        icon="mdi:phone-check",
        value_fn=lambda d: _format_sip_status(d),
    ),
)


def _format_sip_status(dev: dict[str, Any]) -> str:
    """Summarize live SIP account registration states for a device."""
    if not dev.get("is_online"):
        return "Offline"

    statuses = dev.get("accounts_status") or []
    if not statuses:
        return "No Accounts"

    registered = 0
    total = len(statuses)
    for acc in statuses:
        state = str(acc.get("status") or acc.get("registerStatus") or "").lower()
        if state in ("1", "registered", "true", "online"):
            registered += 1

    if registered == total:
        return f"Registered ({registered}/{total})"
    if registered > 0:
        return f"Partial ({registered}/{total})"
    return f"Unregistered (0/{total})"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GDMS sensors from a config entry."""
    coordinator: GdmsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        GdmsAccountSummarySensor(coordinator, entry, "total_devices", "Total Devices", "mdi:devices"),
        GdmsAccountSummarySensor(coordinator, entry, "online_devices", "Online Devices", "mdi:check-network"),
        GdmsAccountSummarySensor(coordinator, entry, "offline_devices", "Offline Devices", "mdi:close-network"),
    ]

    for mac in coordinator.data.get("devices", {}):
        for desc in DEVICE_SENSORS:
            entities.append(GdmsDeviceSensor(coordinator, mac, desc))

    async_add_entities(entities)


class GdmsAccountSummarySensor(CoordinatorEntity[GdmsDataUpdateCoordinator], SensorEntity):
    """Hub-level fleet count sensor for GDMS."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: GdmsDataUpdateCoordinator,
        entry: ConfigEntry,
        metric_key: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the account summary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._metric_key = metric_key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{metric_key}"

    @property
    def native_value(self) -> int:
        return int(self.coordinator.data.get("summary", {}).get(self._metric_key, 0))

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Grandstream Networks",
            model="GDMS Cloud Hub",
        )


class GdmsDeviceSensor(CoordinatorEntity[GdmsDataUpdateCoordinator], SensorEntity):
    """Per-device diagnostic or SIP status sensor."""

    entity_description: GdmsDeviceSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GdmsDataUpdateCoordinator,
        mac: str,
        description: GdmsDeviceSensorDescription,
    ) -> None:
        """Initialize the per-device sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("devices", {}).get(self._mac, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._device_data)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._device_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "sip_registration":
            return None
        dev = self._device_data
        return {
            "accounts_info": dev.get("accounts_info", []),
            "accounts_status": dev.get("accounts_status", []),
        }

    @property
    def device_info(self) -> DeviceInfo:
        dev = self._device_data
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            name=dev.get("deviceName") or f"Grandstream {self._mac}",
            manufacturer="Grandstream Networks",
            model=dev.get("deviceType") or dev.get("model") or "Grandstream Device",
            sw_version=dev.get("firmwareVersion") or dev.get("version"),
            serial_number=dev.get("sn"),
        )
