"""Tuya Cloud AC code-library transport for IR blasters."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from homeassistant.exceptions import HomeAssistantError

from ..const import (
    CONF_TUYA_CLOUD_ACCESS_ID,
    CONF_TUYA_CLOUD_ACCESS_SECRET,
    CONF_TUYA_CLOUD_ENDPOINT,
    CONF_TUYA_CLOUD_MODEL_PACK,
    CONF_TUYA_INFRARED_ID,
    CONF_TUYA_REMOTE_ID,
    DEFAULT_TUYA_CLOUD_ENDPOINT,
)
from ..packs.tuya_cloud.daikin import PACK_ID as DEFAULT_TUYA_CLOUD_PACK_ID

_LOGGER = logging.getLogger(__name__)

EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()

MODE_TO_TUYA = {
    "cool": 0,
    "heat": 1,
    "heat_cool": 2,
    "auto": 2,
    "fan_only": 3,
    "dry": 4,
}

FAN_TO_TUYA_WIND = {
    "auto": 0,
    "low": 1,
    "level1": 1,
    "f1": 1,
    "medium": 2,
    "med": 2,
    "level2": 2,
    "f2": 2,
    "high": 3,
    "level3": 3,
    "level4": 3,
    "level5": 3,
    "f3": 3,
    "f4": 3,
    "f5": 3,
    "powerful": 3,
    "turbo": 3,
}


@dataclass(slots=True)
class TuyaCloudACConfig:
    """Connection details for Tuya Cloud IR AC APIs."""

    endpoint: str
    access_id: str
    access_secret: str
    infrared_id: str
    remote_id: str
    model_pack_id: str = DEFAULT_TUYA_CLOUD_PACK_ID


class TuyaCloudOpenAPI:
    """Minimal Tuya Cloud OpenAPI client for IR AC commands."""

    def __init__(self, hass, config: TuyaCloudACConfig) -> None:
        self._hass = hass
        self._config = config
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    @property
    def endpoint(self) -> str:
        """Return normalized Tuya OpenAPI endpoint."""
        return self._config.endpoint.rstrip("/")

    async def async_send_ac_command(
        self,
        infrared_id: str,
        remote_id: str,
        code: str,
        value: object,
    ) -> None:
        """Send one Tuya AC code-library command."""
        await self._request(
            "POST",
            f"/v2.0/infrareds/{infrared_id}/air-conditioners/{remote_id}/command",
            body={"code": code, "value": value},
            token_required=True,
        )

    async def async_get_ac_status(self, infrared_id: str, remote_id: str) -> dict[str, Any]:
        """Read Tuya's virtual AC status for a bound remote."""
        result = await self._request(
            "GET",
            f"/v2.0/infrareds/{infrared_id}/remotes/{remote_id}/ac/status",
            token_required=True,
        )
        return result if isinstance(result, dict) else {}

    async def _access_token_or_raise(self) -> str:
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        result = await self._request(
            "GET",
            "/v1.0/token",
            query={"grant_type": "1"},
            token_required=False,
        )
        if not isinstance(result, dict) or not result.get("access_token"):
            raise HomeAssistantError("Tuya Cloud token response did not include access_token")

        self._access_token = str(result["access_token"])
        expire_time = int(result.get("expire_time", 7200))
        self._token_expires_at = now + max(60, expire_time - 60)
        return self._access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        token_required: bool,
    ) -> Any:
        method = method.upper()
        body_bytes = _json_body_bytes(body)
        token = await self._access_token_or_raise() if token_required else None
        url_for_sign = _path_with_query(path, query)
        timestamp = str(int(time.time() * 1000))
        content_hash = hashlib.sha256(body_bytes).hexdigest() if body_bytes else EMPTY_BODY_SHA256
        string_to_sign = f"{method}\n{content_hash}\n\n{url_for_sign}"
        sign_seed = self._config.access_id + (token or "") + timestamp + string_to_sign
        signature = hmac.new(
            self._config.access_secret.encode("utf-8"),
            sign_seed.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()

        headers = {
            "client_id": self._config.access_id,
            "sign": signature,
            "sign_method": "HMAC-SHA256",
            "t": timestamp,
            "Content-Type": "application/json",
        }
        if token:
            headers["access_token"] = token

        session = _get_clientsession(self._hass)
        url = f"{self.endpoint}{url_for_sign}"
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                data=body_bytes if body_bytes else None,
            ) as response:
                payload = await response.json(content_type=None)
        except Exception as err:
            raise HomeAssistantError(f"Tuya Cloud request failed for {method} {path}: {err}") from err

        if not isinstance(payload, dict):
            raise HomeAssistantError(f"Tuya Cloud returned non-object response for {method} {path}")

        if not payload.get("success", False):
            code = payload.get("code", "unknown")
            message = payload.get("msg", payload.get("message", "unknown Tuya Cloud error"))
            raise HomeAssistantError(f"Tuya Cloud API error {code}: {message}")

        return payload.get("result")


class TuyaCloudACManager:
    """Send AeroState climate states through Tuya's AC code-library API."""

    def __init__(
        self,
        hass,
        config: TuyaCloudACConfig,
        *,
        api: TuyaCloudOpenAPI | None = None,
    ) -> None:
        self._hass = hass
        self._config = config
        self._api = api or TuyaCloudOpenAPI(hass, config)
        self._last_known_power: bool | None = None
        self._last_mode: str | None = None
        self._last_temperature: int | None = None
        self._last_wind: int | None = None

    async def async_send_climate_state(self, state: dict[str, Any]) -> None:
        """Send only the Tuya AC single commands needed for the requested state."""
        hvac_mode = str(state.get("hvac_mode", "off")).strip().lower()
        wants_power = hvac_mode != "off" and bool(state.get("power", True))

        if not wants_power:
            await self._send_ac_command("power", 0)
            self._last_known_power = False
            return

        mode_value = _mode_value(hvac_mode)
        wind_value = _wind_value(state.get("fan_mode"))
        temperature = _temperature_value(state.get("target_temperature"))

        commands: list[tuple[str, object]] = []
        if self._last_known_power is not True:
            commands.append(("power", 1))
        if self._last_mode != hvac_mode:
            commands.append(("mode", mode_value))
        if hvac_mode != "fan_only" and self._last_temperature != temperature:
            commands.append(("temp", temperature))
        if wind_value is not None and self._last_wind != wind_value:
            commands.append(("wind", wind_value))

        if not commands:
            _LOGGER.debug("TuyaCloudACManager: desired state unchanged: %s", state)
            return

        for code, value in commands:
            await self._send_ac_command(code, value)

        self._last_known_power = True
        self._last_mode = hvac_mode
        if hvac_mode != "fan_only":
            self._last_temperature = temperature
        self._last_wind = wind_value

    async def _send_ac_command(self, code: str, value: object) -> None:
        _LOGGER.debug(
            "TuyaCloudACManager: sending Daikin code-library command %s=%s infrared_id=%s remote_id=%s",
            code,
            value,
            self._config.infrared_id,
            self._config.remote_id,
        )
        await self._api.async_send_ac_command(
            self._config.infrared_id,
            self._config.remote_id,
            code,
            value,
        )

    async def probe_transport(self) -> bool:
        """Check that cloud credentials and Tuya remote IDs are configured and reachable."""
        if not all(
            [
                self._config.endpoint,
                self._config.access_id,
                self._config.access_secret,
                self._config.infrared_id,
                self._config.remote_id,
            ]
        ):
            _LOGGER.warning("Tuya Cloud AC manager is missing required setup fields")
            return False
        try:
            await self._api.async_get_ac_status(self._config.infrared_id, self._config.remote_id)
        except Exception as err:
            _LOGGER.warning("Tuya Cloud AC transport probe failed: %s", err)
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Return diagnostics-safe manager details."""
        return {
            "transport": "tuya_cloud_ac_code_library",
            "endpoint": self._config.endpoint,
            "infrared_id": self._config.infrared_id,
            "remote_id": self._config.remote_id,
            "model_pack_id": self._config.model_pack_id,
            "command_strategy": "single_command_sequence",
        }


def _json_body_bytes(body: dict[str, Any] | None) -> bytes:
    if body is None:
        return b""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _path_with_query(path: str, query: dict[str, str] | None) -> str:
    if not query:
        return path
    return f"{path}?{urlencode(sorted(query.items()))}"


def _mode_value(hvac_mode: str) -> int:
    if hvac_mode not in MODE_TO_TUYA:
        raise HomeAssistantError(f"Tuya Cloud Daikin mode is not supported: {hvac_mode}")
    return MODE_TO_TUYA[hvac_mode]


def _wind_value(fan_mode: object) -> int | None:
    if fan_mode is None:
        return None
    normalized = str(fan_mode).strip().lower().replace(" ", "_").replace("-", "_")
    if normalized not in FAN_TO_TUYA_WIND:
        raise HomeAssistantError(f"Tuya Cloud Daikin fan mode is not supported: {fan_mode}")
    return FAN_TO_TUYA_WIND[normalized]


def _temperature_value(value: object) -> int:
    try:
        temperature = int(round(float(value)))
    except (TypeError, ValueError) as err:
        raise HomeAssistantError("Tuya Cloud Daikin temperature is required") from err
    if temperature < 16 or temperature > 30:
        raise HomeAssistantError("Tuya Cloud Daikin temperature must be between 16 and 30")
    return temperature


def _get_clientsession(hass):
    """Return Home Assistant's shared aiohttp session."""
    try:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
    except ModuleNotFoundError as err:  # pragma: no cover
        raise HomeAssistantError("Home Assistant aiohttp client helper is unavailable") from err
    return async_get_clientsession(hass)


def _entry_value(entry, key: str, default: Any = None) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def create_tuya_cloud_ac_manager_from_entry(hass, entry) -> TuyaCloudACManager:
    """Build a TuyaCloudACManager from a config entry."""
    config = TuyaCloudACConfig(
        endpoint=str(_entry_value(entry, CONF_TUYA_CLOUD_ENDPOINT, DEFAULT_TUYA_CLOUD_ENDPOINT)).strip(),
        access_id=str(_entry_value(entry, CONF_TUYA_CLOUD_ACCESS_ID, "")).strip(),
        access_secret=str(_entry_value(entry, CONF_TUYA_CLOUD_ACCESS_SECRET, "")).strip(),
        infrared_id=str(_entry_value(entry, CONF_TUYA_INFRARED_ID, "")).strip(),
        remote_id=str(_entry_value(entry, CONF_TUYA_REMOTE_ID, "")).strip(),
        model_pack_id=str(
            _entry_value(entry, CONF_TUYA_CLOUD_MODEL_PACK, DEFAULT_TUYA_CLOUD_PACK_ID)
        ).strip()
        or DEFAULT_TUYA_CLOUD_PACK_ID,
    )
    return TuyaCloudACManager(hass, config)


__all__ = [
    "TuyaCloudACConfig",
    "TuyaCloudACManager",
    "TuyaCloudOpenAPI",
    "create_tuya_cloud_ac_manager_from_entry",
]

