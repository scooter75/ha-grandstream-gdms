"""Button platform for Grandstream GDMS remote actions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GdmsApiError
from .const import DOMAIN
from .coordinator import GdmsDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GDMS action buttons from a config entry."""
    coordinator: GdmsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []

    for mac in coordinator.data.get("devices", {}):
        entities.append(GdmsRebootButton(coordinator, mac))
        entities.append(GdmsPushConfigButton(coordinator, mac))

    async_add_entities(entities)


class GdmsBaseButton(CoordinatorEntity[GdmsDataUpdateCoordinator], ButtonEntity):
    """Base button entity for a GDMS device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GdmsDataUpdateCoordinator, mac: str) -> None:
        """Initialize the GDMS button."""
        super().__init__(coordinator)
        self._mac = mac

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("devices", {}).get(self._mac, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._device_data.get("is_online", False))

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


class GdmsRebootButton(GdmsBaseButton):
    """Button to trigger an immediate remote reboot via GDMS."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_name = "Reboot"

    def __init__(self, coordinator: GdmsDataUpdateCoordinator, mac: str) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator, mac)
        self._attr_unique_id = f"{mac}_reboot"

    async def async_press(self) -> None:
        """Send reboot task to GDMS."""
        try:
            await self.coordinator.client.reboot_device(self._mac)
        except GdmsApiError as err:
            raise HomeAssistantError(f"GDMS reboot failed for {self._mac}: {err}") from err


class GdmsPushConfigButton(GdmsBaseButton):
    """Button to push configuration sync to the device via GDMS."""

    _attr_icon = "mdi:cloud-sync"
    _attr_name = "Push Configuration"

    def __init__(self, coordinator: GdmsDataUpdateCoordinator, mac: str) -> None:
        """Initialize the push config button."""
        super().__init__(coordinator, mac)
        self._attr_unique_id = f"{mac}_push_config"

    async def async_press(self) -> None:
        """Send push config task to GDMS."""
        try:
            await self.coordinator.client.push_config(self._mac)
        except GdmsApiError as err:
            raise HomeAssistantError(f"GDMS config push failed for {self._mac}: {err}") from err
