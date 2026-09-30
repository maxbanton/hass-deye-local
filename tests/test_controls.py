"""Settings entities and the verified write path."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.deye_local.models import SINGLE_PHASE

from .test_init import (  # noqa: F401
    _setup,
    auto_enable_custom_integrations,
    bluetooth_device,
    fake_transport,
    transport,
)

PREFIX = "deye_single_phase_hybrid"
MAX_CHARGE = f"number.{PREFIX}_battery_max_charge_current"
ENERGY_PATTERN = f"select.{PREFIX}_energy_pattern"
TIME_OF_USE = f"switch.{PREFIX}_time_of_use"


def control(key: str):
    return next(c for c in SINGLE_PHASE.controls if c.key == key)


async def _call(hass: HomeAssistant, domain: str, service: str, entity_id: str, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )


async def test_settings_are_shown_as_the_inverter_reports_them(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get(MAX_CHARGE).state == "40"
    assert hass.states.get(f"number.{PREFIX}_grid_charge_current").state == "40"
    assert hass.states.get(f"number.{PREFIX}_battery_max_discharge_current") is None
    assert hass.states.get(f"number.{PREFIX}_battery_shutdown_soc").state == "10"
    assert hass.states.get(ENERGY_PATTERN).state == "load_first"
    assert hass.states.get(f"select.{PREFIX}_work_mode").state == "zero_export_to_load"
    assert hass.states.get(TIME_OF_USE).state == "on"
    assert hass.states.get(f"switch.{PREFIX}_grid_charge").state == "on"
    assert hass.states.get(f"time.{PREFIX}_tou_slot_1_time").state == "01:00:00"
    assert hass.states.get(f"time.{PREFIX}_tou_slot_6_time").state == "21:00:00"
    assert hass.states.get(f"number.{PREFIX}_tou_slot_6_soc").state == "100"
    assert hass.states.get(f"number.{PREFIX}_tou_slot_1_power") is None


async def test_number_write_is_verified_and_shown(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _call(hass, "number", "set_value", MAX_CHARGE, value=50)
    assert transport().writes == [(0x00D2, [50])]
    assert hass.states.get(MAX_CHARGE).state == "50"


async def test_select_writes_the_register_code(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _call(hass, "select", "select_option", ENERGY_PATTERN, option="battery_first")
    assert transport().writes == [(0x00F3, [0])]
    assert hass.states.get(ENERGY_PATTERN).state == "battery_first"


async def test_switch_on_a_bit_keeps_the_other_bits(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _call(hass, "switch", "turn_off", TIME_OF_USE)
    assert transport().writes == [(0x00F8, [0x00FE])]
    assert hass.states.get(TIME_OF_USE).state == "off"


async def test_write_starts_from_the_inverters_current_value(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    # Generator charge was turned on at the inverter since the last poll.
    fake.registers[0x0112] = 0x0007
    await entry.runtime_data.async_write_control(control("tou1_grid_charge"), 0)
    assert fake.writes == [(0x0112, [0x0006])]


async def test_unchanged_value_is_not_written(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _call(hass, "number", "set_value", MAX_CHARGE, value=40)
    assert transport().writes == []


async def test_value_the_inverter_does_not_keep_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    transport().ignored_writes.add(0x00D2)
    with (
        patch("custom_components.deye_local.coordinator.WRITE_VERIFY_TIMEOUT", 0),
        pytest.raises(HomeAssistantError, match="did not keep"),
    ):
        await _call(hass, "number", "set_value", MAX_CHARGE, value=200)
    assert hass.states.get(MAX_CHARGE).state == "40"


async def test_write_failure_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    transport().fail = True
    with pytest.raises(HomeAssistantError, match="Could not change"):
        await _call(hass, "number", "set_value", MAX_CHARGE, value=50)


async def test_tou_times_must_stay_in_order(hass: HomeAssistant) -> None:
    await _setup(hass)
    entity_id = f"time.{PREFIX}_tou_slot_2_time"
    for bad in ("00:30:00", "09:00:00"):
        with pytest.raises(ServiceValidationError):
            await _call(hass, "time", "set_value", entity_id, time=bad)
    await _call(hass, "time", "set_value", entity_id, time="04:30:00")
    assert transport().writes == [(0x00FB, [430])]
    assert hass.states.get(entity_id).state == "04:30:00"


async def test_changes_made_on_the_inverter_show_up_on_the_settings_read(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    fake = transport()
    fake.registers[0x00D2] = 60
    await coordinator.async_refresh()
    assert hass.states.get(MAX_CHARGE).state == "40"
    coordinator._last_settings_read = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(MAX_CHARGE).state == "60"


async def test_settings_are_not_read_on_every_poll(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    fake.reads.clear()
    await entry.runtime_data.async_refresh()
    assert not any(0x00C8 <= start <= 0x0117 for start, _ in fake.reads)


async def test_tou_power_is_bounded_by_the_rated_power(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass)
    entity_id = f"number.{PREFIX}_tou_slot_1_power"
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "6000"
    assert state.attributes["max"] == 6000


async def test_experimental_family_has_no_controls(hass: HomeAssistant) -> None:
    await _setup(hass, device_type=5)
    for domain in ("number", "select", "switch", "time"):
        assert hass.states.async_entity_ids(domain) == []


def test_time_codec() -> None:
    from custom_components.deye_local.time import decode_time, encode_time

    assert decode_time(2130) == time(21, 30)
    assert decode_time(2460) is None
    assert encode_time(time(5, 5)) == 505


async def test_percentages_are_sliders_and_currents_boxes(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get(f"number.{PREFIX}_tou_slot_6_soc").attributes["mode"] == "slider"
    assert hass.states.get(f"number.{PREFIX}_battery_shutdown_soc").attributes["mode"] == "slider"
    assert hass.states.get(MAX_CHARGE).attributes["mode"] == "box"


async def test_sell_power_is_bounded_by_the_rated_power(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass)
    registry = er.async_get(hass)
    for key in ("max_sell_power", "zero_export_power"):
        registry.async_update_entity(f"number.{PREFIX}_{key}", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    sell = hass.states.get(f"number.{PREFIX}_max_sell_power")
    assert (sell.state, sell.attributes["max"]) == ("6000", 6000)
    assert hass.states.get(f"number.{PREFIX}_zero_export_power").state == "45"


async def test_bms_sensors_are_disabled_by_default(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    await _setup(hass)
    entity_id = f"sensor.{PREFIX}_bms_soc"
    entry = er.async_get(hass).async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_grid_peak_shaving_uses_bit_8_only(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    fake = transport()
    await entry.runtime_data.async_write_control(control("grid_peak_shaving"), 1)
    # Captured from the inverter screen: ticking grid peak shaving set only bit 8.
    assert fake.writes == [(0x0118, [0x6110])]
    await entry.runtime_data.async_write_control(control("grid_peak_shaving"), 0)
    assert fake.writes[-1] == (0x0118, [0x6010])
