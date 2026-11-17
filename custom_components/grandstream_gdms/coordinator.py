"""DataUpdateCoordinator for Grandstream GDMS."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GdmsApiClient, GdmsApiError, GdmsAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class GdmsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to poll GDMS cloud devices and account statuses."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: GdmsApiClient,
        org_id: int | None,
        scan_interval: int,
    ) -> None:
        """Initialize the GDMS coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.org_id = org_id
        self._account_info_cache: dict[str, list[dict[str, Any]]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest devices, sites, and SIP statuses from GDMS."""
        try:
            raw_devices = await self.client.get_devices(org_id=self.org_id)
            sites = await self.client.get_sites(org_id=self.org_id)
        except GdmsAuthError as err:
            raise ConfigEntryAuthFailed(f"GDMS authentication failed: {err}") from err
        except GdmsApiError as err:
            raise UpdateFailed(f"Error communicating with GDMS API: {err}") from err

        site_map: dict[Any, str] = {
            site["id"]: site.get("siteName", f"Site {site['id']}")
            for site in sites
            if "id" in site
        }

        devices_by_mac: dict[str, dict[str, Any]] = {}
        online_count = 0
        offline_count = 0

        for dev in raw_devices:
            mac = self.client.normalize_mac(dev.get("mac", ""))
            if not mac:
                continue

            status_raw = dev.get("status")
            is_online = status_raw in (1, "1", "online", "ONLINE", True)
            if is_online:
                online_count += 1
            else:
                offline_count += 1

            if mac not in self._account_info_cache:
                self._account_info_cache[mac] = await self.client.get_device_account_info(mac)

            account_statuses: list[dict[str, Any]] = []
            if is_online:
                account_statuses = await self.client.get_device_account_status(mac)

            site_id = dev.get("siteId")
            enriched = {
                **dev,
                "mac": mac,
                "is_online": is_online,
                "site_name": dev.get("siteName") or site_map.get(site_id, "Default"),
                "accounts_info": self._account_info_cache.get(mac, []),
                "accounts_status": account_statuses,
            }
            devices_by_mac[mac] = enriched

        return {
            "devices": devices_by_mac,
            "sites": sites,
            "summary": {
                "total_devices": len(devices_by_mac),
                "online_devices": online_count,
                "offline_devices": offline_count,
                "total_sites": len(sites),
            },
        }
