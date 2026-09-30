"""On/off inverter settings."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .control import DeyeControlEntity, controls_for
from .models import ControlPlatform

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DeyeSwitch(coordinator, control)
        for control in controls_for(coordinator, ControlPlatform.SWITCH)
    )


class DeyeSwitch(DeyeControlEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        raw = self.raw_value
        return None if raw is None else raw != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_write(0)
