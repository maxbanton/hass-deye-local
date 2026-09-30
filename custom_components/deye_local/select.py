"""Inverter settings with a fixed set of choices."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .control import DeyeControlEntity, controls_for
from .coordinator import DeyeLocalCoordinator
from .models import Control, ControlPlatform

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DeyeSelect(coordinator, control)
        for control in controls_for(coordinator, ControlPlatform.SELECT)
    )


class DeyeSelect(DeyeControlEntity, SelectEntity):
    def __init__(self, coordinator: DeyeLocalCoordinator, control: Control) -> None:
        super().__init__(coordinator, control)
        self._attr_options = list(control.options.values())
        self._codes = {option: code for code, option in control.options.items()}

    @property
    def current_option(self) -> str | None:
        raw = self.raw_value
        return None if raw is None else self.control.options.get(raw)

    async def async_select_option(self, option: str) -> None:
        await self.async_write(self._codes[option])
