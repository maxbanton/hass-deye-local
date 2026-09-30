"""Sensors decoded from the inverter's registers."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeyeLocalConfigEntry
from .coordinator import DeyeLocalCoordinator
from .entity import (
    DeyeBatteryEntity,
    DeyeLocalEntity,
    async_register_device,
    module_device_info,
)
from .models import (
    DEVICE_STATES,
    REG_DEVICE_TYPE,
    Kind,
    RegisterSensor,
    battery_sensor,
    battery_sensors,
    decode,
    describe_codes,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeyeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        DeyeRegisterSensor(coordinator, sensor) for sensor in coordinator.family.sensors
    ]
    entities.append(SignalStrengthSensor(coordinator, "signal_strength"))
    async_add_entities(entities)

    known: set[str] = set()

    @callback
    def _add_new_batteries() -> None:
        for serial, index in coordinator.battery_slots.items():
            if serial not in known:
                async_register_device(
                    hass, entry, module_device_info(index, serial), coordinator.inverter_device_id
                )
        new = [
            BatteryModuleSensor(coordinator, index, serial, sensor)
            for serial, index in coordinator.battery_slots.items()
            if serial not in known
            for sensor in battery_sensors(index)
        ]
        known.update(coordinator.battery_slots)
        if new:
            async_add_entities(new)

    _add_new_batteries()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_batteries))


class _RegisterValue:
    """Shared behaviour; listed first so its availability check wraps the coordinator's."""

    sensor: RegisterSensor

    def _describe(self, sensor: RegisterSensor) -> None:
        self.sensor = sensor
        self._attr_native_unit_of_measurement = sensor.unit
        self._attr_device_class = sensor.device_class
        self._attr_state_class = sensor.state_class
        self._attr_suggested_display_precision = sensor.precision
        self._attr_entity_registry_enabled_default = sensor.enabled
        if sensor.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if sensor.kind is Kind.STATE:
            self._attr_translation_key = sensor.key
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = DEVICE_STATES
        else:
            self._attr_name = sensor.name

    @property
    def native_value(self) -> Any:
        return decode(self.sensor, self.coordinator.data or {})

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None


class DeyeRegisterSensor(_RegisterValue, DeyeLocalEntity, SensorEntity):
    def __init__(self, coordinator: DeyeLocalCoordinator, sensor: RegisterSensor) -> None:
        super().__init__(coordinator, sensor.key)
        self._describe(sensor)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        if self.sensor.kind in (Kind.ALARM, Kind.FAULT):
            return describe_codes(self.sensor, data)
        if self.sensor.kind is Kind.DEVICE_TYPE and REG_DEVICE_TYPE in data:
            return {"code": f"{data[REG_DEVICE_TYPE]:#06x}"}
        return None


class BatteryModuleSensor(_RegisterValue, DeyeBatteryEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DeyeLocalCoordinator,
        index: int,
        serial: str,
        sensor: RegisterSensor,
    ) -> None:
        super().__init__(coordinator, index, serial, sensor.key)
        self._describe(sensor)

    @property
    def native_value(self) -> Any:
        # Modules can change slots; read wherever this serial currently sits.
        index = self.coordinator.battery_slots.get(self.serial)
        if index is None:
            return None
        return decode(battery_sensor(index, self.sensor.key), self.coordinator.data or {})


class SignalStrengthSensor(DeyeLocalEntity, SensorEntity):
    """How strongly the adapter or proxy carrying the link hears the logger."""

    _attr_translation_key = "signal_strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        return self.coordinator.rssi

    @property
    def available(self) -> bool:
        return self.coordinator.rssi is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {"source": self.coordinator.source}
