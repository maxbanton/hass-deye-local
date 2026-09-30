"""Config flow for Deye Local."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_DEVICE_TYPE,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_KEEP_CONNECTED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SERVICE_UUID,
)
from .models import IDENTITY_BLOCK, REG_DEVICE_TYPE, REG_SERIAL, Support, family_for
from .protocol import decode_ascii
from .transport import DeyeTransport, TransportError


@dataclass
class Identity:
    device_type: int
    serial: str


async def async_identify(info: BluetoothServiceInfoBleak) -> Identity:
    transport = DeyeTransport(info.device)
    try:
        await transport.async_connect()
        words = await transport.async_read(*IDENTITY_BLOCK)
    finally:
        await transport.async_disconnect()
    start, count = IDENTITY_BLOCK
    regs = dict(zip(range(start, start + count), words, strict=True))
    return Identity(
        device_type=regs[REG_DEVICE_TYPE],
        serial=decode_ascii([regs[r] for r in REG_SERIAL]),
    )


SUPPORT_TEXT = {
    Support.SUPPORTED: "Supported.",
    Support.EXPERIMENTAL: (
        "Experimental: the register map for this family is not yet confirmed on real "
        "hardware. Values are read only; please report anything that looks wrong."
    ),
    Support.UNSUPPORTED: (
        "Not supported yet. The device is added with its identity only, so you can "
        "download diagnostics (they include a register dump) and open an issue to get "
        "this model added."
    ),
}


def _is_logger(info: BluetoothServiceInfoBleak) -> bool:
    return SERVICE_UUID in info.service_uuids


def _display_name(info: BluetoothServiceInfoBleak) -> str:
    """The logger advertises its serial as its name, but only in scan responses."""
    if info.name and info.name.replace("-", ":").upper() != info.address.upper():
        return info.name
    return f"Deye data logger {info.address}"


class DeyeLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Deye inverter through its WiBLE logger."""

    VERSION = 1

    def __init__(self) -> None:
        self._info: BluetoothServiceInfoBleak | None = None
        self._identity: Identity | None = None
        self._candidates: dict[str, BluetoothServiceInfoBleak] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DeyeLocalOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._info = discovery_info
        self.context["title_placeholders"] = {"name": _display_name(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask before connecting: the logger has a single connection slot."""
        assert self._info is not None
        if user_input is not None:
            return await self.async_step_identify()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"logger": _display_name(self._info)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._info = self._candidates[user_input[CONF_ADDRESS]]
            await self.async_set_unique_id(self._info.address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_identify()

        configured = self._async_current_ids(include_ignore=False)
        self._candidates = {
            info.address: info
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if _is_logger(info) and info.address not in configured
        }
        if not self._candidates:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{_display_name(info)} ({info.rssi} dBm)"
                            for address, info in self._candidates.items()
                        }
                    )
                }
            ),
        )

    async def async_step_identify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the inverter behind the logger; offer a retry if it cannot be reached."""
        assert self._info is not None
        try:
            self._identity = await async_identify(self._info)
        except TransportError:
            return self.async_show_form(
                step_id="identify",
                errors={"base": "cannot_connect"},
                description_placeholders={"logger": _display_name(self._info)},
            )
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._info is not None and self._identity is not None
        family = family_for(self._identity.device_type)
        if user_input is not None:
            return self.async_create_entry(
                title=f"Deye {family.name}",
                data={
                    CONF_ADDRESS: self._info.address,
                    CONF_DEVICE_TYPE: self._identity.device_type,
                    CONF_SERIAL: self._identity.serial,
                },
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "logger": _display_name(self._info),
                "model": family.name,
                "serial": self._identity.serial or "unknown",
                "support": SUPPORT_TEXT[family.support],
            },
        )


class DeyeLocalOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Required(
                        CONF_KEEP_CONNECTED,
                        default=options.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED),
                    ): bool,
                }
            ),
        )
