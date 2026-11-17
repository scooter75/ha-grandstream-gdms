"""The Grandstream GDMS integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GdmsApiClient, GdmsApiError
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ORG_ID,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXEC_TYPE_IMMEDIATE,
    PLATFORMS,
    SERVICE_ADD_TASK,
    SERVICE_PUSH_CONFIG,
    SERVICE_REBOOT_DEVICE,
)
from .coordinator import GdmsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("mac"): cv.string,
    }
)

SERVICE_ADD_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("mac_list"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("task_type"): vol.Coerce(int),
        vol.Required("task_name"): cv.string,
        vol.Optional("exec_type", default=EXEC_TYPE_IMMEDIATE): vol.Coerce(int),
    }
)


def _resolve_mac_from_call(hass: HomeAssistant, call: ServiceCall) -> str:
    """Resolve a device MAC address from either 'mac' or HA 'device_id'."""
    if mac := call.data.get("mac"):
        return GdmsApiClient.normalize_mac(mac)

    if device_id := call.data.get("device_id"):
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device:
            for domain, identifier in device.identifiers:
                if domain == DOMAIN:
                    return GdmsApiClient.normalize_mac(identifier)

    raise HomeAssistantError("A valid 'mac' or Grandstream GDMS 'device_id' must be provided.")


def _get_first_coordinator(hass: HomeAssistant) -> GdmsDataUpdateCoordinator:
    """Return the first active GDMS coordinator."""
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("No configured Grandstream GDMS integration instances found.")
    return next(iter(entries.values()))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grandstream GDMS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = GdmsApiClient(
        session=session,
        region=entry.data.get(CONF_REGION, DEFAULT_REGION),
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    org_id = entry.data.get(CONF_ORG_ID)

    coordinator = GdmsDataUpdateCoordinator(
        hass=hass,
        client=client,
        org_id=org_id,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _async_register_services(hass)
    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-wide GDMS services once."""
    if hass.services.has_service(DOMAIN, SERVICE_REBOOT_DEVICE):
        return

    async def handle_reboot_device(call: ServiceCall) -> None:
        mac = _resolve_mac_from_call(hass, call)
        coordinator = _get_first_coordinator(hass)
        try:
            await coordinator.client.reboot_device(mac)
        except GdmsApiError as err:
            raise HomeAssistantError(f"Failed to reboot device {mac}: {err}") from err

    async def handle_push_config(call: ServiceCall) -> None:
        mac = _resolve_mac_from_call(hass, call)
        coordinator = _get_first_coordinator(hass)
        try:
            await coordinator.client.push_config(mac)
        except GdmsApiError as err:
            raise HomeAssistantError(f"Failed to push config to {mac}: {err}") from err

    async def handle_add_task(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        try:
            await coordinator.client.add_task(
                mac_list=call.data["mac_list"],
                task_type=call.data["task_type"],
                task_name=call.data["task_name"],
                exec_type=call.data["exec_type"],
            )
        except GdmsApiError as err:
            raise HomeAssistantError(f"Failed to create GDMS task: {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT_DEVICE, handle_reboot_device, schema=SERVICE_DEVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PUSH_CONFIG, handle_push_config, schema=SERVICE_DEVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_TASK, handle_add_task, schema=SERVICE_ADD_TASK_SCHEMA
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REBOOT_DEVICE)
            hass.services.async_remove(DOMAIN, SERVICE_PUSH_CONFIG)
            hass.services.async_remove(DOMAIN, SERVICE_ADD_TASK)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
