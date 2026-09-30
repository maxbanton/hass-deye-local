"""Base for entities that change inverter settings."""
from __future__ import annotations

from homeassistant.const import EntityCategory

from .coordinator import DeyeLocalCoordinator
from .entity import DeyeLocalEntity
from .models import Control, ControlPlatform, control_value


def controls_for(
    coordinator: DeyeLocalCoordinator, platform: ControlPlatform
) -> list[Control]:
    return [c for c in coordinator.family.controls if c.platform is platform]


class DeyeControlEntity(DeyeLocalEntity):
    def __init__(self, coordinator: DeyeLocalCoordinator, control: Control) -> None:
        super().__init__(coordinator, control.key)
        self.control = control
        self._attr_entity_registry_enabled_default = control.enabled
        if control.options:
            self._attr_translation_key = control.key
        else:
            self._attr_name = control.name
        if control.config:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def raw_value(self) -> int | None:
        return control_value(self.control, self.coordinator.data or {})

    @property
    def available(self) -> bool:
        return super().available and self.raw_value is not None

    async def async_write(self, value: int) -> None:
        await self.coordinator.async_write_control(self.control, value)
