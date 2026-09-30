"""Numeric inverter settings."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .const import DOMAIN
from .control import DeyeControlEntity, controls_for
from .coordinator import DeyeLocalCoordinator
from .models import Control, ControlPlatform, rated_power

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DeyeNumber(coordinator, control)
        for control in controls_for(coordinator, ControlPlatform.NUMBER)
    )


class DeyeNumber(DeyeControlEntity, NumberEntity):
    def __init__(self, coordinator: DeyeLocalCoordinator, control: Control) -> None:
        super().__init__(coordinator, control)
        self._attr_mode = NumberMode.SLIDER if control.slider else NumberMode.BOX
        self._attr_native_min_value = control.minimum
        self._attr_native_step = control.step
        self._attr_native_unit_of_measurement = control.unit
        if control.device_class:
            self._attr_device_class = NumberDeviceClass(control.device_class)

    @property
    def native_max_value(self) -> float:
        if self.control.maximum is not None:
            return self.control.maximum
        # Wide enough for any model until the rated power has been read; the
        # inverter still rejects what it cannot do.
        return rated_power(self.coordinator.family, self.coordinator.data or {}) or 65535

    @property
    def native_value(self) -> float | None:
        raw = self.raw_value
        if raw is None:
            return None
        return round(raw * self.control.scale, 2)

    async def async_set_native_value(self, value: float) -> None:
        raw = round(value / self.control.scale)
        if not 0 <= raw <= 0xFFFF:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_of_range",
                translation_placeholders={"name": self.control.name, "value": str(value)},
            )
        await self.async_write(raw)
