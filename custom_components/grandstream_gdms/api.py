"""Async API client for Grandstream Device Management System (GDMS)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_DEVICE_ACCOUNT_INFO,
    API_DEVICE_ACCOUNT_STATUS,
    API_DEVICE_LIST,
    API_OAUTH_TOKEN,
    API_ORG_LIST,
    API_SITE_LIST,
    API_TASK_ADD,
    EXEC_TYPE_IMMEDIATE,
    TASK_TYPE_CONFIG_PUSH,
    TASK_TYPE_REBOOT,
)

_LOGGER = logging.getLogger(__name__)


class GdmsApiError(Exception):
    """Base exception for GDMS API errors."""

    def __init__(self, message: str, ret_code: int | None = None) -> None:
        super().__init__(message)
        self.ret_code = ret_code


class GdmsAuthError(GdmsApiError):
    """Exception raised when authentication or token refresh fails."""


class GdmsApiClient:
    """Asynchronous client for Grandstream GDMS OpenAPI."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize the GDMS API client."""
        self._session = session
        self._base_url = f"https://{region}"
        self._client_id = str(client_id).strip()
        self._client_secret = str(client_secret).strip()
        self._username = str(username).strip()
        self._password = password

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0.0

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash password per GDMS spec: SHA256(MD5(password))."""
        md5_hex = hashlib.md5(password.encode("utf-8")).hexdigest()
        return hashlib.sha256(md5_hex.encode("utf-8")).hexdigest()

    @staticmethod
    def _sha256(value: str) -> str:
        """Return lowercase SHA-256 hex digest."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def authenticate(self) -> None:
        """Obtain an OAuth2 access token using password grant."""
        url = f"{self._base_url}{API_OAUTH_TOKEN}"
        payload = {
            "username": self._username,
            "password": self._hash_password(self._password),
            "grant_type": "password",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self._session.post(
                url, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GdmsApiError(f"Connection error during authentication: {err}") from err

        if "access_token" not in data:
            error_desc = data.get("error_description") or data.get("msg") or str(data)
            raise GdmsAuthError(f"GDMS authentication failed: {error_desc}")

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = time.monotonic() + max(expires_in - 120, 60)

    async def refresh_access_token(self) -> None:
        """Refresh the OAuth2 access token, falling back to full auth on failure."""
        if not self._refresh_token:
            await self.authenticate()
            return

        url = f"{self._base_url}{API_OAUTH_TOKEN}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self._session.post(
                url, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json(content_type=None)
        except aiohttp.ClientError:
            await self.authenticate()
            return

        if "access_token" not in data:
            await self.authenticate()
            return

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = time.monotonic() + max(expires_in - 120, 60)

    async def _ensure_token(self) -> str:
        """Ensure a valid access token is available."""
        if not self._access_token or time.monotonic() >= self._token_expires_at:
            if self._refresh_token:
                await self.refresh_access_token()
            else:
                await self.authenticate()
        assert self._access_token is not None
        return self._access_token

    def _build_signature(self, token: str, timestamp_ms: int, body_str: str | None) -> str:
        """Build the GDMS SHA-256 request signature."""
        base = (
            f"&access_token={token}"
            f"&client_id={self._client_id}"
            f"&client_secret={self._client_secret}"
            f"&timestamp={timestamp_ms}&"
        )
        if body_str:
            body_hash = self._sha256(body_str)
            base = f"{base}{body_hash}&"
        return self._sha256(base)

    async def _request(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] | list[Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Execute a signed request against the GDMS OpenAPI."""
        token = await self._ensure_token()
        timestamp_ms = int(time.time() * 1000)

        body_str: str | None = None
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        signature = self._build_signature(token, timestamp_ms, body_str)
        params = {
            "access_token": token,
            "signature": signature,
            "timestamp": str(timestamp_ms),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}{endpoint}"

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                data=body_str.encode("utf-8") if body_str else None,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                result = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GdmsApiError(f"GDMS request to {endpoint} failed: {err}") from err

        ret_code = result.get("retCode")
        if ret_code == 0:
            return result

        if retry_auth and ret_code in (40001, 40002, 401, 10002):
            _LOGGER.debug("GDMS token expired (retCode=%s), refreshing token", ret_code)
            self._access_token = None
            await self.authenticate()
            return await self._request(method, endpoint, body=body, retry_auth=False)

        msg = result.get("msg") or "Unknown GDMS API error"
        if ret_code in (40001, 40002, 40003):
            raise GdmsAuthError(f"GDMS auth/signature error ({ret_code}): {msg}", ret_code)
        raise GdmsApiError(f"GDMS API error ({ret_code}): {msg}", ret_code)

    async def get_organizations(self) -> list[dict[str, Any]]:
        """Retrieve all accessible GDMS organizations."""
        res = await self._request("GET", API_ORG_LIST)
        return res.get("data", {}).get("result", [])

    async def get_sites(self, org_id: int | None = None) -> list[dict[str, Any]]:
        """Retrieve sites for the account or specified organization."""
        body = {"orgId": org_id} if org_id is not None else None
        method = "POST" if body else "GET"
        res = await self._request(method, API_SITE_LIST, body=body)
        return res.get("data", {}).get("result", [])

    async def get_devices(self, org_id: int | None = None) -> list[dict[str, Any]]:
        """Fetch all managed devices across paginated GDMS responses."""
        devices: list[dict[str, Any]] = []
        page_num = 1
        page_size = 100

        while True:
            payload: dict[str, Any] = {
                "pageNum": page_num,
                "pageSize": page_size,
            }
            if org_id is not None:
                payload["orgId"] = org_id

            res = await self._request("POST", API_DEVICE_LIST, body=payload)
            data = res.get("data") or {}
            page_items = data.get("result") or []
            devices.extend(page_items)

            total = int(data.get("total", len(devices)))
            if len(devices) >= total or not page_items:
                break
            page_num += 1

        return devices

    async def get_device_account_info(self, mac: str) -> list[dict[str, Any]]:
        """Fetch configured SIP accounts/extensions for a device MAC."""
        clean_mac = self.normalize_mac(mac)
        try:
            res = await self._request("POST", API_DEVICE_ACCOUNT_INFO, body={"mac": clean_mac})
            data = res.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("result", [])
        except GdmsApiError as err:
            _LOGGER.debug("Account info unavailable for %s: %s", clean_mac, err)
        return []

    async def get_device_account_status(self, mac: str) -> list[dict[str, Any]]:
        """Fetch live SIP account registration status for a device MAC."""
        clean_mac = self.normalize_mac(mac)
        try:
            res = await self._request("POST", API_DEVICE_ACCOUNT_STATUS, body={"mac": clean_mac})
            data = res.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("result", [])
        except GdmsApiError as err:
            _LOGGER.debug("Account status unavailable for %s: %s", clean_mac, err)
        return []

    async def add_task(
        self,
        mac_list: list[str],
        task_type: int,
        task_name: str,
        exec_type: int = EXEC_TYPE_IMMEDIATE,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Schedule or immediately execute a GDMS device task."""
        normalized_macs = [self.normalize_mac(m) for m in mac_list]
        payload: dict[str, Any] = {
            "taskName": task_name,
            "taskType": task_type,
            "macList": normalized_macs,
            "execType": exec_type,
        }
        if extra_params:
            payload.update(extra_params)

        return await self._request("POST", API_TASK_ADD, body=payload)

    async def reboot_device(self, mac: str) -> dict[str, Any]:
        """Trigger an immediate reboot task for a device MAC."""
        return await self.add_task(
            mac_list=[mac],
            task_type=TASK_TYPE_REBOOT,
            task_name=f"HA_REBOOT_{self.normalize_mac(mac)}",
            exec_type=EXEC_TYPE_IMMEDIATE,
        )

    async def push_config(self, mac: str) -> dict[str, Any]:
        """Trigger an immediate configuration sync/push task for a device MAC."""
        return await self.add_task(
            mac_list=[mac],
            task_type=TASK_TYPE_CONFIG_PUSH,
            task_name=f"HA_CONFIG_PUSH_{self.normalize_mac(mac)}",
            exec_type=EXEC_TYPE_IMMEDIATE,
        )

    @staticmethod
    def normalize_mac(mac: str) -> str:
        """Format MAC address as uppercase colon-separated XX:XX:XX:XX:XX:XX."""
        raw = "".join(ch for ch in mac.upper() if ch in "0123456789ABCDEF")
        if len(raw) == 12:
            return ":".join(raw[i : i + 2] for i in range(0, 12, 2))
        return mac.upper().strip()
