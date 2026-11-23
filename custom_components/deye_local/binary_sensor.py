"""Status bits reported by the inverter."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .coordinator import DeyeLocalCoordinator
from .entity import DeyeLocalEntity
from .models import RegisterFlag

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DeyeFlag(coordinator, flag) for flag in coordinator.family.flags)


class DeyeFlag(DeyeLocalEntity, BinarySensorEntity):
    def __init__(self, coordinator: DeyeLocalCoordinator, flag: RegisterFlag) -> None:
        super().__init__(coordinator, flag.key)
        self.flag = flag
        self._attr_translation_key = flag.key
        self._attr_entity_registry_enabled_default = flag.enabled

    @property
    def is_on(self) -> bool | None:
        raw = (self.coordinator.data or {}).get(self.flag.register)
        return None if raw is None else bool(raw >> self.flag.bit & 1)

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None
