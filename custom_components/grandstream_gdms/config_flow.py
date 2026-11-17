"""Config flow for Grandstream GDMS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GdmsApiClient, GdmsApiError, GdmsAuthError
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ORG_ID,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)


class GdmsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grandstream GDMS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}
        self._orgs: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = GdmsApiClient(
                session=session,
                region=user_input[CONF_REGION],
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )

            try:
                await client.authenticate()
                self._orgs = await client.get_organizations()
            except GdmsAuthError:
                errors["base"] = "invalid_auth"
            except GdmsApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception validating GDMS credentials")
                errors["base"] = "unknown"
            else:
                self._user_input = user_input
                if len(self._orgs) > 1:
                    return await self.async_step_org()

                org_id = self._orgs[0]["id"] if self._orgs else None
                org_name = self._orgs[0].get("organization", "Default") if self._orgs else "Default"
                return await self._create_gdms_entry(org_id=org_id, org_name=org_name)

        schema = vol.Schema(
            {
                vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(REGIONS),
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_org(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle organization selection when multiple GDMS organizations exist."""
        org_options: dict[str, str] = {"all": "All Organizations"}
        for org in self._orgs:
            org_options[str(org["id"])] = f"{org.get('organization', 'Org')} (ID: {org['id']})"

        if user_input is not None:
            selected = user_input[CONF_ORG_ID]
            if selected == "all":
                return await self._create_gdms_entry(org_id=None, org_name="All Organizations")
            org_id = int(selected)
            org_name = org_options.get(selected, f"Org {org_id}")
            return await self._create_gdms_entry(org_id=org_id, org_name=org_name)

        return self.async_show_form(
            step_id="org",
            data_schema=vol.Schema({vol.Required(CONF_ORG_ID, default="all"): vol.In(org_options)}),
        )

    async def _create_gdms_entry(self, org_id: int | None, org_name: str) -> ConfigFlowResult:
        """Create the config entry with a unique ID."""
        unique_id = f"{self._user_input[CONF_REGION]}_{self._user_input[CONF_USERNAME]}_{org_id or 'all'}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        data = {
            **self._user_input,
            CONF_ORG_ID: org_id,
        }
        title = f"GDMS ({org_name})"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GdmsOptionsFlowHandler:
        """Return the options flow handler."""
        return GdmsOptionsFlowHandler(config_entry)


class GdmsOptionsFlowHandler(OptionsFlow):
    """Handle GDMS options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    )
                }
            ),
        )
