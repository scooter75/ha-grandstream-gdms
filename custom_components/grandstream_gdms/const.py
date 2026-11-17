"""Constants for the Grandstream GDMS integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "grandstream_gdms"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.BUTTON,
]

CONF_REGION = "region"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_ORG_ID = "org_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_REGION = "www.gdms.cloud"
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

REGIONS: dict[str, str] = {
    "www.gdms.cloud": "World / Americas (www.gdms.cloud)",
    "eu.gdms.cloud": "Europe (eu.gdms.cloud)",
    "oc.gdms.cloud": "Oceania (oc.gdms.cloud)",
}

# GDMS OpenAPI Endpoints
API_OAUTH_TOKEN = "/oapi/oauth/token"
API_ORG_LIST = "/oapi/v1.0.0/org/list"
API_SITE_LIST = "/oapi/v1.0.0/site/list"
API_DEVICE_LIST = "/oapi/v1.0.0/device/list"
API_DEVICE_ACCOUNT_INFO = "/oapi/v1.0.0/device/account/info"
API_DEVICE_ACCOUNT_STATUS = "/oapi/v1.0.0/device/account/status"
API_TASK_ADD = "/oapi/v1.0.0/task/add"

# GDMS Task Types
TASK_TYPE_REBOOT = 1
TASK_TYPE_UPGRADE = 2
TASK_TYPE_CONFIG_PUSH = 3

# Task Execution Types
EXEC_TYPE_IMMEDIATE = 1

# Services
SERVICE_REBOOT_DEVICE = "reboot_device"
SERVICE_PUSH_CONFIG = "push_config"
SERVICE_ADD_TASK = "add_task"
