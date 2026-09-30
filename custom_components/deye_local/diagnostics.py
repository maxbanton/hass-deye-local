"""Diagnostics, including a register dump that helps map new inverter families.

Serial numbers and the logger's address are redacted, also where they appear as
raw register values, because users are asked to share this file publicly.
"""
from __future__ import annotations

import re
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import DeyeLocalConfigEntry
from .const import CONF_SERIAL
from .models import MAX_BATTERIES, REG_SERIAL, battery_serial_block
from .transport import TransportError

TO_REDACT = {CONF_ADDRESS, CONF_SERIAL}
_MAC = re.compile(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")


def _serial_registers() -> set[int]:
    registers = set(REG_SERIAL)
    for index in range(MAX_BATTERIES):
        start, count = battery_serial_block(index)
        registers.update(range(start, start + count))
    return registers


def _redact_dump(dump: dict[str, Any], hidden: set[int]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, values in dump.items():
        if isinstance(values, list):
            start = int(key, 16)
            values = [
                REDACTED if start + offset in hidden else value
                for offset, value in enumerate(values)
            ]
        redacted[key] = values
    return redacted


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeyeLocalConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    family = coordinator.family
    info = bluetooth.async_last_service_info(hass, coordinator.address, connectable=True)
    hidden = _serial_registers()

    try:
        dump = await coordinator.async_dump()
    except TransportError as err:
        dump = {"error": str(err)}

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "family": {
            "key": family.key,
            "name": family.name,
            "support": family.support.value,
        },
        "logger": {
            "name": REDACTED if info and info.name else None,
            "rssi": info.rssi if info else None,
            "source": _MAC.sub(REDACTED, coordinator.source) if coordinator.source else None,
            "handshake": coordinator.transport.logger_type,
        },
        "last_error": coordinator.last_error,
        "batteries": [
            {"slot": index + 1, "serial": REDACTED}
            for index in sorted(coordinator.battery_slots.values())
        ],
        "polled_registers": {
            f"{address:04X}": REDACTED if address in hidden else value
            for address, value in sorted((coordinator.data or {}).items())
        },
        "register_dump": _redact_dump(dump, hidden),
    }
