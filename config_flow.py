"""Config flow for MotionBlinds BLE integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import FlowResult
from homeassistant.exceptions import HomeAssistantError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.wrappers import HaBleakScannerWrapper, BLEDevice
from homeassistant.core import callback
from bleak import BleakScanner, BleakClient

import re

from .const import (
    DOMAIN,
    CONF_ADDRESS,
    CONF_LOCAL_NAME,
    CONF_MAC,
    CONF_BLIND_TYPE,
    MotionBlindType,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required("MAC"): str})


def is_valid_mac(data: str) -> bool:
    """Validate the provided MAC address."""

    mac_regex = r"^[0-9A-Fa-f]{4}$"
    return bool(re.match(mac_regex, data))


def get_mac_from_local_name(data: str) -> str:
    """Gets the MAC address from the bluetooth local name."""

    mac_regex = r"^MOTION_([0-9A-Fa-f]{4})$"
    match = re.search(mac_regex, data)
    return match.group(1) if match else None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MotionBlinds BLE."""

    VERSION = 1

    _discovery_info: BluetoothServiceInfoBleak = None
    _mac: str = None
    _display_name: str = None
    _blind_type: MotionBlindType = None
    # motionblinds_discovery_result = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        _LOGGER.debug(
            "Discovered Motion bluetooth device: %s", discovery_info.as_dict()
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["local_name"] = discovery_info.name
        self._discovery_info = discovery_info
        self._mac = get_mac_from_local_name(discovery_info.name)
        self._display_name = f"MotionBlind {self._mac}"
        self.context["title_placeholders"] = {"name": self._display_name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a single device."""
        if user_input is not None:
            self._blind_type = user_input[CONF_BLIND_TYPE]
            return await self._async_create_entry_from_discovery(user_input)

        # self._set_confirm_only()
        # return self.async_show_form(
        #     step_id="confirm",
        #     data_schema=vol.Schema({}),
        #     description_placeholders={"name": self._display_name},
        # )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BLIND_TYPE): vol.In(
                        {
                            MotionBlindType.POSITION: "Position",
                            MotionBlindType.POSITION_TILT: "Position & Tilt",
                        }
                    )
                }
            ),
            description_placeholders={"display_name": self._display_name},
        )

    async def _async_create_entry_from_discovery(
        self, user_input: dict[str, Any]
    ) -> FlowResult:
        """Create an entry from a discovery."""

        return self.async_create_entry(
            title=self._display_name,
            data={
                CONF_ADDRESS: self._discovery_info.address,
                CONF_LOCAL_NAME: self._discovery_info.name,
                CONF_MAC: self._mac,
                CONF_BLIND_TYPE: self._blind_type,
            },
        )

    # async def async_step_integration_discovery(
    #     self, discovery_info: DiscoveryInfoType
    # ) -> FlowResult:
    #     _LOGGER.debug("Found integration")
    #     return await super().async_step_integration_discovery(discovery_info)

    # async def async_step_user(
    #     self, user_input: dict[str, Any] | None = None
    # ) -> FlowResult:
    #     """Handle a flow initialized by the user."""
    #     errors: dict[str, str] = {}
    #     if user_input is not None:
    #         mac = user_input["MAC"]
    #         if not is_valid_mac(mac):
    #             errors["base"] = "invalid_mac"
    #         else:
    #             # Discover with BLE
    #             self._motionblinds_discovery_result = (
    #                 await self._async_discover_motionblind(mac)
    #             )

    #             return await self._async_step_found_motionblind(mac)

    #     # Return and show error
    #     return self.async_show_form(
    #         step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
    #     )

    # async def _async_step_found_motionblind(self, mac) -> FlowResult:
    #     _LOGGER.warning("Finishing 3")
    #     res = self._motionblinds_discovery_result
    #     if res is NoBluetoothAdapter:
    #         errors: dict[str, str] = {}
    #         errors["base"] = "no_bluetooth_adapter"
    #         return self.async_show_form(
    #             step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
    #         )
    #     elif res is CouldNotFindMAC:
    #         errors: dict[str, str] = {}
    #         errors["base"] = "could_not_find_mac"
    #         return self.async_show_form(
    #             step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
    #         )
    #     return self.async_create_entry(title="Some title", data={})

    # async def _async_discover_motionblind(self, mac: str):
    #     # Discover
    #     # await asyncio.sleep(2)  # A task that take some time to complete

    #     motionblind_address = CouldNotFindMAC

    #     count = bluetooth.async_scanner_count(self.hass, connectable=True)
    #     if count == 0:
    #         self.hass.async_create_task(
    #             self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
    #         )
    #         _LOGGER.error("Could not find any bluetooth adapter.")
    #         return NoBluetoothAdapter

    #     try:
    #         _LOGGER.warning(count)
    #         _LOGGER.warning("Getting scanner")
    #         bleak_scanner = bluetooth.async_get_scanner(self.hass)
    #         _LOGGER.warning("Discovering")
    #         # No timeout?
    #         devices = await bleak_scanner.discover()
    #         _LOGGER.warning("Finished discovery")

    #     except Exception as e:
    #         _LOGGER.error(e)

    #     _LOGGER.warning(devices)

    #     motionDevice = None

    #     for device in devices:
    #         if f"MOTION_{mac.upper()}" in device.name:
    #             motionDevice = device.name
    #             motionblind_address = device.address

    #     _LOGGER.warning(f"Found motion device: {motionDevice}")

    #     _LOGGER.warning("Finishing")
    #     return motionblind_address

    # async def async_step_progress_done(self, user_input=None) -> FlowResult:
    #     # Show progress can only transition to show progress or show progress done.
    #     _LOGGER.warning("Finishing 2")
    #     return self.async_show_progress_done(next_step_id="finish")

    # @callback
    # def _async_motionblind_found(
    #     service_info: bluetooth.BluetoothServiceInfoBleak,
    #     change: bluetooth.BluetoothChange,
    # ):
    #     _LOGGER.log("Found")

    # async def async_step_discover_motionblind(
    #     self, user_input: dict[str, Any] | None = None
    # ) -> FlowResult:
    #     mac = user_input["MAC"]

    #     return bluetooth.async_register_callback(
    #         self.hass,
    #         self._async_motionblind_found,
    #         {"local_name": f"MOTION_{mac}"},
    #         bluetooth.BluetoothScanningMode.ACTIVE,
    #     )
    #     # return self.async_create_entry(title="info["title"]", data=user_input)


class NoBluetoothAdapter(HomeAssistantError):
    """No bluetooth adapter."""


class InvalidMAC(HomeAssistantError):
    """Error to indicate the MAC code is invalid."""


class CouldNotFindMAC(HomeAssistantError):
    """Error to indicate the MAC code is invalid."""
