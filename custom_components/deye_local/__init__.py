"""The Deye Local integration: Deye inverters over the WiBLE logger's Bluetooth link."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

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
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]
ISSUES_URL = "https://github.com/maxbanton/hass-deye-local/issues"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type DeyeLocalConfigEntry = ConfigEntry[DeyeLocalCoordinator]


FRONTEND_URL = f"/{DOMAIN}/frontend"
FRONTEND_PATH = Path(__file__).parent / "frontend"
CARD_FILE = "deye-local-tou-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the time of use card and load it on every dashboard.

    The frontend is only an after-dependency, so setups without it (tests,
    headless installs) still load the integration.
    """
    if "frontend" not in hass.config.components or hass.http is None:
        return
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(FRONTEND_PATH), True)]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL}/{CARD_FILE}?v={version}")


def _issue_id(entry: ConfigEntry) -> str:
    return f"model_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: DeyeLocalConfigEntry) -> bool:
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

    if family.support is Support.SUPPORTED:
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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


async def _async_reload(hass: HomeAssistant, entry: DeyeLocalConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


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
