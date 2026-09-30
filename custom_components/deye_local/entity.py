"""Devices and base entities for Deye Local: the inverter and its battery modules."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL, DOMAIN, MANUFACTURER
from .coordinator import DeyeLocalCoordinator


def inverter_identifier(coordinator: DeyeLocalCoordinator) -> str:
    data = coordinator.config_entry.data
    return data.get(CONF_SERIAL) or data[CONF_ADDRESS]


def inverter_device_info(coordinator: DeyeLocalCoordinator) -> DeviceInfo:
    data = coordinator.config_entry.data
    return DeviceInfo(
        identifiers={(DOMAIN, inverter_identifier(coordinator))},
        connections={(CONNECTION_BLUETOOTH, data[CONF_ADDRESS])},
        manufacturer=MANUFACTURER,
        model=coordinator.family.name,
        serial_number=data.get(CONF_SERIAL),
        name=f"Deye {coordinator.family.name}",
    )


def module_device_info(index: int, serial: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"battery_{serial}")},
        model="Battery module",
        serial_number=serial,
        name=f"Deye battery {index + 1}",
    )


@callback
def async_register_device(
    hass: HomeAssistant, entry: ConfigEntry, info: DeviceInfo, parent_id: str | None
) -> str:
    """Create a device, link it to its parent, and return its id.

    Linking through the registry by device id works on every supported Home
    Assistant version, unlike passing the parent in DeviceInfo.
    """
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, **info)
    if parent_id is not None and device.via_device_id != parent_id:
        registry.async_update_device(device.id, via_device_id=parent_id)
    return device.id


class DeyeLocalEntity(CoordinatorEntity[DeyeLocalCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DeyeLocalCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{inverter_identifier(coordinator)}_{key}"
        self._attr_device_info = inverter_device_info(coordinator)


class DeyeBatteryEntity(CoordinatorEntity[DeyeLocalCoordinator]):
    """An entity on one battery module's device, identified by the module's serial."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: DeyeLocalCoordinator, index: int, serial: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self.serial = serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = module_device_info(index, serial)
