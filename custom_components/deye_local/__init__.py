"""The Deye Local integration: Deye inverters over the WiBLE logger's Bluetooth link."""
from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .card import async_add_card_resource, async_remove_card_resource, async_serve_card
from .const import (
    CONF_DEVICE_TYPE,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEEP_CONNECTED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import DeyeLocalCoordinator
from .entity import async_register_device, inverter_device_info, inverter_identifier
from .models import Support, family_for
from .services import async_setup_services

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]
ISSUES_URL = "https://github.com/maxbanton/hass-deye-local/issues"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type DeyeLocalConfigEntry = ConfigEntry[DeyeLocalCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    await async_serve_card(hass)
    return True


def _issue_id(entry: ConfigEntry) -> str:
    return f"model_{entry.entry_id}"


@callback
def _enable_default_controls(hass: HomeAssistant, coordinator: DeyeLocalCoordinator) -> None:
    """Enable controls an older version registered as disabled by default.

    Home Assistant applies a default only when it first registers an entity, so
    a control that became enabled by default would stay off for existing users.
    Controls the user disabled are left alone.
    """
    registry = er.async_get(hass)
    prefix = f"{inverter_identifier(coordinator)}_"
    enabled = {control.key for control in coordinator.family.controls if control.enabled}
    for entity in er.async_entries_for_config_entry(registry, coordinator.config_entry.entry_id):
        if (
            entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            and entity.unique_id.startswith(prefix)
            and entity.unique_id.removeprefix(prefix) in enabled
        ):
            registry.async_update_entity(entity.entity_id, disabled_by=None)


async def async_setup_entry(hass: HomeAssistant, entry: DeyeLocalConfigEntry) -> bool:
    await async_add_card_resource(hass)
    address = entry.data[CONF_ADDRESS]
    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="not_in_range",
            translation_placeholders={"address": address},
        )

    family = family_for(entry.data[CONF_DEVICE_TYPE])
    coordinator = DeyeLocalCoordinator(
        hass,
        entry,
        device,
        family,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        entry.options.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await coordinator.transport.async_close()
        raise
    entry.runtime_data = coordinator
    # Battery module devices hang off the inverter, so it has to exist first.
    coordinator.inverter_device_id = async_register_device(
        hass, entry, inverter_device_info(coordinator), None
    )

    @callback
    def _seen(info: BluetoothServiceInfoBleak, _change: BluetoothChange) -> None:
        coordinator.update_advertisement(info)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _seen,
            BluetoothCallbackMatcher(address=address, connectable=True),
            BluetoothScanningMode.PASSIVE,
        )
    )

    # Only a family without entities gets a repair issue: it explains the empty device.
    if family.support is not Support.UNSUPPORTED:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=family.support.value,
            translation_placeholders={"model": family.name, "url": ISSUES_URL},
        )

    _enable_default_controls(hass, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    options = dict(entry.options)

    async def _async_reload(hass: HomeAssistant, entry: DeyeLocalConfigEntry) -> None:
        # Detected units are saved to the entry data, which needs no reload.
        if entry.options != options:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        # 1.1 kept the session open by default, which stops the logger's cloud
        # uploads. Stored values only exist because the options form saves every
        # field, so drop them and let the new defaults apply; a deliberately
        # slower poll interval stays.
        options = dict(entry.options)
        options.pop(CONF_KEEP_CONNECTED, None)
        if options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL) < DEFAULT_SCAN_INTERVAL:
            del options[CONF_SCAN_INTERVAL]
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeyeLocalConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.transport.async_close()
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: DeyeLocalConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting any device except the inverter and battery modules still reported."""
    coordinator = entry.runtime_data
    in_use = {inverter_identifier(coordinator)} | {
        f"battery_{serial}" for serial in coordinator.battery_slots
    }
    return not any(
        domain == DOMAIN and ident in in_use for domain, ident in device.identifiers
    )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))
    if not any(
        other.entry_id != entry.entry_id for other in hass.config_entries.async_entries(DOMAIN)
    ):
        await async_remove_card_resource(hass)
