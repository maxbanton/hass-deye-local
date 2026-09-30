"""Polling coordinator for one data logger."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BATTERY_SCAN_INTERVAL,
    DOMAIN,
    MAX_BLOCK,
    SETTINGS_INTERVAL,
    STALE_TIMEOUT,
    WRITE_VERIFY_DELAY,
    WRITE_VERIFY_TIMEOUT,
)
from .models import (
    IDENTITY_BLOCK,
    MAX_BATTERIES,
    Control,
    Family,
    battery_sensors,
    battery_serial_block,
    with_control_value,
)
from .protocol import decode_ascii, plan_blocks
from .transport import DeyeTransport, RegisterUnavailable, TransportError

_LOGGER = logging.getLogger(__name__)

DUMP_RANGES = ((0x0000, 0x0180), (0x01F4, 0x02E0), (0x2710, 0x27F0))


class DeyeLocalCoordinator(DataUpdateCoordinator[dict[int, int]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: BLEDevice,
        family: Family,
        scan_interval: int,
        keep_connected: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.address = device.address
        self.family = family
        self.keep_connected = keep_connected
        self.transport = DeyeTransport(device)
        self.blocks = plan_blocks(family.registers, MAX_BLOCK) or [IDENTITY_BLOCK]
        self.settings_blocks = plan_blocks(family.setting_registers, MAX_BLOCK)
        self._settings: dict[int, int] = {}
        self._last_settings_read: float | None = None
        self.inverter_device_id: str | None = None
        # Battery module serial -> slot index.
        self.battery_slots: dict[str, int] = {}
        self._scan_batteries = family.has_battery_modules
        self._last_battery_scan: float | None = None
        self._registers: dict[int, int] = {}
        self._last_success = 0.0
        self.last_error: str | None = None
        # One poll or diagnostics sweep at a time over the single session.
        self._session_lock = asyncio.Lock()
        self.rssi: int | None = None
        self.source: str | None = None

    def update_advertisement(self, info: BluetoothServiceInfoBleak) -> None:
        """Track the logger's latest advertisement: route and signal strength."""
        self.transport.set_device(info.device)
        self.rssi = info.rssi
        scanner = bluetooth.async_scanner_by_source(self.hass, info.source)
        self.source = scanner.name if scanner is not None else info.source

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.transport.async_close()

    def _stale_limit(self) -> float:
        interval = self.update_interval.total_seconds() if self.update_interval else 0
        return max(STALE_TIMEOUT, 2 * interval)

    async def _async_update_data(self) -> dict[int, int]:
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        if info is not None:
            self.update_advertisement(info)
        async with self._session_lock:
            try:
                await self.transport.async_connect()
                if self._battery_scan_due():
                    await self._async_scan_batteries()
                if self._settings_due():
                    self._settings = await self._async_read(self.settings_blocks)
                    self._last_settings_read = time.monotonic()
                snapshot = {**self._settings, **await self._async_read(self.blocks)}
            except TransportError as err:
                self.last_error = str(err)
                await self.transport.async_disconnect()
                if self._registers and time.monotonic() - self._last_success < self._stale_limit():
                    _LOGGER.debug("Poll failed, serving last values: %s", err)
                    return self._registers
                raise UpdateFailed(str(err)) from err
            if not self.keep_connected:
                await self.transport.async_disconnect()
        self._registers = snapshot
        self._last_success = time.monotonic()
        self.last_error = None
        return snapshot

    def _settings_due(self) -> bool:
        if not self.settings_blocks:
            return False
        last = self._last_settings_read
        return last is None or time.monotonic() - last >= SETTINGS_INTERVAL

    async def _async_read(self, blocks: list[tuple[int, int]]) -> dict[int, int]:
        snapshot: dict[int, int] = {}
        for start, count in blocks:
            try:
                values = await self.transport.async_read(start, count)
            except RegisterUnavailable:
                # Usually a battery module that has just been removed; its values
                # go unavailable and the modules are rescanned on the next poll.
                _LOGGER.debug("Registers %#06x+%d unavailable", start, count)
                self._last_battery_scan = None
                continue
            snapshot.update(zip(range(start, start + count), values, strict=True))
        return snapshot

    def _battery_scan_due(self) -> bool:
        if not self._scan_batteries:
            return False
        last = self._last_battery_scan
        return last is None or time.monotonic() - last >= BATTERY_SCAN_INTERVAL

    async def _async_scan_batteries(self) -> None:
        slots: dict[str, int] = {}
        missing = 0
        for index in range(MAX_BATTERIES):
            try:
                words = await self.transport.async_read(*battery_serial_block(index))
            except RegisterUnavailable:
                missing += 1
                continue
            serial = decode_ascii(words, swapped=True)
            if not serial or len(set(serial)) == 1:
                continue
            if serial in slots:
                _LOGGER.warning(
                    "Battery modules in slots %d and %d report the same serial %s",
                    slots[serial] + 1, index + 1, serial,
                )
                continue
            slots[serial] = index
        if missing == MAX_BATTERIES:
            self._scan_batteries = False
        self._last_battery_scan = time.monotonic()
        if slots != self.battery_slots:
            _LOGGER.debug("Battery modules: %s", slots)
            self.battery_slots = slots
            registers = set(self.family.registers)
            for index in slots.values():
                registers.update(r for s in battery_sensors(index) for r in s.registers)
            self.blocks = plan_blocks(registers, MAX_BLOCK)

    async def async_write_control(self, control: Control, value: int) -> None:
        """Write one control and confirm the inverter kept it.

        The register is read first so that bits outside the control, and changes
        made on the inverter since the last poll, are preserved.
        """
        register = control.register
        async with self._session_lock:
            try:
                await self.transport.async_connect()
                (current,) = await self.transport.async_read(register, 1)
                target = with_control_value(control, current, value)
                if target != current:
                    _LOGGER.debug(
                        "Writing %s: register %#06x %d -> %d",
                        control.key, register, current, target,
                    )
                    await self.transport.async_write(register, [target])
                    current = await self._async_read_back(register, target)
            except TransportError as err:
                await self.transport.async_disconnect()
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="write_failed",
                    translation_placeholders={"name": control.name, "error": str(err)},
                ) from err
            finally:
                if not self.keep_connected:
                    await self.transport.async_disconnect()
        self._settings[register] = current
        if self.data is not None:
            self.async_set_updated_data({**self.data, register: current})
        if current != target:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_not_applied",
                translation_placeholders={"name": control.name},
            )

    async def _async_read_back(self, register: int, target: int) -> int:
        deadline = time.monotonic() + WRITE_VERIFY_TIMEOUT
        while True:
            (value,) = await self.transport.async_read(register, 1)
            if value == target or time.monotonic() >= deadline:
                return value
            await asyncio.sleep(WRITE_VERIFY_DELAY)

    async def async_dump(self) -> dict[str, Any]:
        """Sweep the dump ranges; stop at the first failure that is not a missing register."""
        dump: dict[str, Any] = {}
        async with self._session_lock:
            try:
                await self.transport.async_connect()
                for first, last in DUMP_RANGES:
                    for start in range(first, last, MAX_BLOCK):
                        count = min(MAX_BLOCK, last - start)
                        try:
                            dump[f"{start:04X}"] = await self.transport.async_read(start, count)
                        except RegisterUnavailable as err:
                            dump[f"{start:04X}"] = f"unavailable: {err}"
            except TransportError as err:
                dump["error"] = str(err)
                await self.transport.async_disconnect()
            finally:
                if not self.keep_connected:
                    await self.transport.async_disconnect()
        return dump
