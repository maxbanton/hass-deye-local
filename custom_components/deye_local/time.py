"""Time of use slot start times.

Each slot runs from its start time until the next slot's, so the six start
times have to stay in ascending order.
"""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .const import DOMAIN
from .control import DeyeControlEntity, controls_for
from .models import Control, ControlPlatform, control_value

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DeyeTime(coordinator, control)
        for control in controls_for(coordinator, ControlPlatform.TIME)
    )


def decode_time(raw: int) -> time | None:
    hours, minutes = divmod(raw, 100)
    if hours > 23 or minutes > 59:
        return None
    return time(hours, minutes)


def encode_time(value: time) -> int:
    return value.hour * 100 + value.minute


class DeyeTime(DeyeControlEntity, TimeEntity):
    @property
    def native_value(self) -> time | None:
        raw = self.raw_value
        return None if raw is None else decode_time(raw)

    def _neighbours(self) -> tuple[int | None, int | None]:
        slots: list[Control] = [
            c for c in self.coordinator.family.controls
            if c.platform is ControlPlatform.TIME
        ]
        index = slots.index(self.control)
        data = self.coordinator.data or {}
        before = control_value(slots[index - 1], data) if index > 0 else None
        after = control_value(slots[index + 1], data) if index + 1 < len(slots) else None
        return before, after

    async def async_set_value(self, value: time) -> None:
        raw = encode_time(value)
        before, after = self._neighbours()
        if (before is not None and raw <= before) or (after is not None and raw >= after):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="tou_order",
                translation_placeholders={"name": self.control.name},
            )
        await self.async_write(raw)
