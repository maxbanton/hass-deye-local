"""Setup, polling, unload and battery module tests."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deye_local import async_remove_config_entry_device
from custom_components.deye_local.const import (
    CONF_DEVICE_TYPE,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DOMAIN,
)

from .common import ADDRESS, FakeTransport, service_info
from .snapshot import BATTERIES

BATTERY_1 = "25007000E4020510"
BATTERY_2 = "25007000E1260830"
SLOT_1 = range(0x2730, 0x2756)
SLOT_2 = range(0x2756, 0x277C)

SOC = "sensor.deye_single_phase_hybrid_battery_soc"
STATE = "sensor.deye_single_phase_hybrid_device_state"
FAULT = "sensor.deye_single_phase_hybrid_fault"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture(autouse=True)
def bluetooth_device(enable_bluetooth):
    info = service_info()
    with (
        patch(
            "custom_components.deye_local.bluetooth.async_ble_device_from_address",
            return_value=info.device,
        ),
        patch(
            "custom_components.deye_local.coordinator.bluetooth.async_last_service_info",
            return_value=info,
        ),
    ):
        yield info


@pytest.fixture(autouse=True)
def fake_transport():
    FakeTransport.instances.clear()
    with patch("custom_components.deye_local.coordinator.DeyeTransport", FakeTransport):
        yield


def transport() -> FakeTransport:
    return FakeTransport.instances[-1]


async def _setup(hass: HomeAssistant, device_type: int = 3) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_DEVICE_TYPE: device_type, CONF_SERIAL: "2603125693"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_reads_the_mapped_registers(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SOC).state == "86"
    assert hass.states.get(STATE).state == "normal"
    assert hass.states.get(FAULT).state == "OK"
    device_type = hass.states.get("sensor.deye_single_phase_hybrid_device_type")
    assert device_type.state == "Single phase hybrid"
    assert device_type.attributes["code"] == "0x0003"
    assert all(count <= 16 for _, count in transport().reads)


async def test_per_poll_mode_releases_the_logger_between_polls(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_DEVICE_TYPE: 3, CONF_SERIAL: "2603125693"},
        options={CONF_KEEP_CONNECTED: False},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fake = transport()
    assert not fake.connected
    await entry.runtime_data.async_refresh()
    assert (fake.connects, fake.disconnects) == (2, 2)
    assert hass.states.get(SOC).state == "86"


async def test_persistent_mode_keeps_one_session(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await entry.runtime_data.async_refresh()
    assert (transport().connects, transport().disconnects) == (1, 0)


async def test_signal_strength_reports_the_link(hass: HomeAssistant) -> None:
    await _setup(hass)
    state = hass.states.get("sensor.deye_single_phase_hybrid_signal_strength")
    assert state.state == "-60"
    assert state.attributes["unit_of_measurement"] == "dBm"
    assert state.attributes["source"] == "local"


async def test_logger_out_of_range_retries_setup(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.deye_local.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_one_failed_poll_keeps_the_last_values(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    transport().fail = True
    await coordinator.async_refresh()
    assert hass.states.get(SOC).state == "86"
    assert transport().disconnects == 1


async def test_values_go_unavailable_after_the_stale_timeout(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    transport().fail = True
    with patch(
        "custom_components.deye_local.coordinator.time.monotonic",
        return_value=coordinator._last_success + 61,
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(SOC).state == STATE_UNAVAILABLE


async def test_experimental_family_raises_a_repair_issue(hass: HomeAssistant) -> None:
    entry = await _setup(hass, device_type=0x0005)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"model_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "experimental"


async def test_unsupported_family_exposes_identity_only(hass: HomeAssistant) -> None:
    entry = await _setup(hass, device_type=0x0004)
    assert entry.state is ConfigEntryState.LOADED
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"model_{entry.entry_id}")
    assert issue.translation_key == "unsupported"
    assert transport().reads == [(0, 3)]


async def test_unload_releases_the_logger(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not transport().connected


def _battery_devices(hass: HomeAssistant) -> dict[str, dr.DeviceEntry]:
    return {
        device.serial_number: device
        for device in dr.async_get(hass).devices.values()
        if device.model == "Battery module"
    }


async def _rescan(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.runtime_data._last_battery_scan = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_battery_modules_become_devices(hass: HomeAssistant) -> None:
    await _setup(hass)
    inverter = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "2603125693")})
    devices = _battery_devices(hass)
    assert set(devices) == {BATTERY_1, BATTERY_2}
    assert all(device.via_device_id == inverter.id for device in devices.values())
    assert hass.states.get("sensor.deye_single_phase_hybrid_bms_soc") is not None

    assert hass.states.get("sensor.deye_battery_1_soc").state == "87.6"
    assert hass.states.get("sensor.deye_battery_1_current").state == "-4.0"
    assert hass.states.get("sensor.deye_battery_1_cell_voltage_difference").state == "4"
    assert hass.states.get("sensor.deye_battery_2_soc").state == "90.5"
    assert hass.states.get("sensor.deye_battery_2_cycles").state == "3"


async def test_battery_added_later_appears_without_reload(hass: HomeAssistant) -> None:
    with patch.object(FakeTransport, "__init__", _one_battery):
        entry = await _setup(hass)
    assert set(_battery_devices(hass)) == {BATTERY_1}
    assert hass.states.get("sensor.deye_battery_2_soc") is None

    transport().registers.update({a: BATTERIES[a] for a in SLOT_2})
    await _rescan(hass, entry)
    assert set(_battery_devices(hass)) == {BATTERY_1, BATTERY_2}
    assert hass.states.get("sensor.deye_battery_2_soc").state == "90.5"


async def test_removed_battery_goes_unavailable_and_can_be_deleted(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    for address in SLOT_1:
        transport().registers[address] = 0
    await _rescan(hass, entry)

    assert hass.states.get("sensor.deye_battery_1_soc").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.deye_battery_2_soc").state == "90.5"
    devices = _battery_devices(hass)
    assert await async_remove_config_entry_device(hass, entry, devices[BATTERY_1])
    assert not await async_remove_config_entry_device(hass, entry, devices[BATTERY_2])
    inverter = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "2603125693")})
    assert not await async_remove_config_entry_device(hass, entry, inverter)


async def test_module_moving_slots_keeps_its_entities(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    for offset in range(0x26):
        fake.registers[0x2730 + offset] = BATTERIES[0x2756 + offset]
        fake.registers[0x2756 + offset] = BATTERIES[0x2730 + offset]
    await _rescan(hass, entry)
    assert entry.runtime_data.battery_slots == {BATTERY_2: 0, BATTERY_1: 1}
    # Entity ids follow the serial, not the slot.
    assert hass.states.get("sensor.deye_battery_2_soc").state == "90.5"
    assert hass.states.get("sensor.deye_battery_1_soc").state == "87.6"


async def test_inverter_without_battery_registers(hass: HomeAssistant) -> None:
    with patch.object(FakeTransport, "__init__", _no_battery_area):
        entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert _battery_devices(hass) == {}
    reads = len(transport().reads)
    await _rescan(hass, entry)
    assert not any(start >= 0x2700 for start, _ in transport().reads[reads:])


_original_init = FakeTransport.__init__


def _no_battery_area(self, device, registers=None):
    _original_init(self, device, registers)
    self.unavailable_from = 0x2700


def _one_battery(self, device, registers=None):
    _original_init(self, device, registers)
    for address in SLOT_2:
        self.registers[address] = 0


async def test_transient_error_while_scanning_keeps_modules(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    fake.busy_from = 0x2700
    await _rescan(hass, entry)
    assert entry.runtime_data._scan_batteries
    fake.busy_from = None
    await _rescan(hass, entry)
    assert set(entry.runtime_data.battery_slots) == {BATTERY_1, BATTERY_2}


async def test_removed_module_reported_missing_does_not_fail_the_poll(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    transport().unavailable_blocks = {0x2730}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.last_update_success
    assert hass.states.get(SOC).state == "86"
    assert hass.states.get("sensor.deye_battery_1_soc").state == STATE_UNAVAILABLE

    await entry.runtime_data.async_refresh()  # the removal triggers a rescan
    await hass.async_block_till_done()
    assert entry.runtime_data.battery_slots == {BATTERY_2: 1}
    assert entry.runtime_data._scan_batteries
    assert hass.states.get("sensor.deye_battery_2_soc").state == "90.5"


async def test_placeholder_and_duplicate_serials_are_ignored(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    for offset in range(8):
        fake.registers[0x277C + offset] = BATTERIES[0x2756 + offset]  # slot 3 copies slot 2
        fake.registers[0x27A2 + offset] = 0x3030  # slot 4 reads "0000..."
    await _rescan(hass, entry)
    assert entry.runtime_data.battery_slots == {BATTERY_1: 0, BATTERY_2: 1}


async def test_stale_window_covers_long_poll_intervals(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_DEVICE_TYPE: 3, CONF_SERIAL: "2603125693"},
        options={CONF_SCAN_INTERVAL: 120},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    transport().fail = True
    with patch(
        "custom_components.deye_local.coordinator.time.monotonic",
        return_value=coordinator._last_success + 130,
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(SOC).state == "86"


async def test_diagnostics_sweep_in_per_poll_mode_releases_the_logger(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_DEVICE_TYPE: 3, CONF_SERIAL: "2603125693"},
        options={CONF_KEEP_CONNECTED: False},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    dump, _ = await asyncio.gather(coordinator.async_dump(), coordinator.async_refresh())
    assert not any(isinstance(v, str) for v in dump.values())
    assert not transport().connected


async def test_unload_closes_the_transport(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert fake.closed
