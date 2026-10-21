"""The set_tou_schedule action: the whole table in as few writes as possible."""
from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.deye_local.const import DOMAIN

from .test_init import (  # noqa: F401
    _setup,
    auto_enable_custom_integrations,
    bluetooth_device,
    fake_transport,
    transport,
)

PREFIX = "deye_single_phase_hybrid"

# As the snapshot holds it: SOC 85 in slots 1-5, charge registers 5 (grid charge
# plus an unknown bit 2 that has to survive).
CURRENT = [
    {"time": "01:00", "power": 6000, "batt": 85, "grid_charge": True, "gen": False},
    {"time": "05:00", "power": 6000, "batt": 85, "grid_charge": True, "gen": False},
    {"time": "09:00", "power": 6000, "batt": 85, "grid_charge": True, "gen": False},
    {"time": "13:00", "power": 6000, "batt": 85, "grid_charge": True, "gen": False},
    {"time": "17:00", "power": 6000, "batt": 85, "grid_charge": True, "gen": False},
    {"time": "21:00", "power": 6000, "batt": 100, "grid_charge": True, "gen": False},
]


def schedule(**changes: dict) -> list[dict]:
    slots = [dict(slot) for slot in CURRENT]
    for key, values in changes.items():
        slots[int(key[-1]) - 1].update(values)
    return slots


async def _set(hass: HomeAssistant, slots: list[dict], **data) -> None:
    await hass.services.async_call(
        DOMAIN, "set_tou_schedule", {"slots": slots, **data}, blocking=True
    )


async def test_unchanged_schedule_writes_nothing(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule())
    assert transport().writes == []


async def test_changes_go_out_in_one_frame(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule(slot3={"batt": 65}, slot4={"batt": 65}))
    assert transport().writes == [(0x010E, [65, 65])]
    assert hass.states.get(f"number.{PREFIX}_tou_slot_3_soc").state == "65"
    assert hass.states.get(f"number.{PREFIX}_tou_slot_4_soc").state == "65"


async def test_times_can_move_past_their_old_neighbours(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule(slot2={"time": "10:00"}, slot3={"time": "11:00"}))
    assert transport().writes == [(0x00FB, [1000, 1100])]
    assert hass.states.get(f"time.{PREFIX}_tou_slot_2_time").state == "10:00:00"


async def test_whole_table_is_one_frame(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule(slot1={"time": "00:30"}, slot6={"gen": True}))
    ((start, values),) = transport().writes
    assert start == 0x00FA
    assert len(values) == 0x0117 - 0x00FA + 1
    assert values[0] == 30
    assert values[-1] == 7


async def test_charge_flags_keep_the_other_bits(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule(slot1={"grid_charge": False}, slot2={"gen": True}))
    assert transport().writes == [(0x0112, [4, 7])]


async def test_voltage_is_optional_and_scaled(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, schedule(slot1={"voltage": 50.5}))
    assert transport().writes == [(0x0106, [5050])]


async def test_logger_that_refuses_long_writes_gets_one_frame_per_column(
    hass: HomeAssistant,
) -> None:
    await _setup(hass)
    fake = transport()
    fake.max_write = 6
    await _set(hass, schedule(slot1={"time": "00:30"}, slot6={"batt": 90}))
    assert fake.writes == [(0x00FA, [30]), (0x0111, [90])]
    fake.writes.clear()
    await _set(hass, schedule(slot1={"time": "00:45"}, slot6={"batt": 95}))
    assert fake.writes == [(0x00FA, [45]), (0x0111, [95])]


async def test_out_of_order_times_are_rejected(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError, match="increase"):
        await _set(hass, schedule(slot3={"time": "04:00"}))
    assert transport().writes == []


async def test_power_above_rated_is_rejected(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await _set(hass, schedule(slot2={"power": 7000}))
    assert transport().writes == []


async def test_exactly_six_slots(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(vol.Invalid):
        await _set(hass, CURRENT[:5])


async def test_value_the_inverter_does_not_keep_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    transport().ignored_writes.add(0x010E)
    with (
        patch("custom_components.deye_local.coordinator.WRITE_VERIFY_TIMEOUT", 0),
        pytest.raises(HomeAssistantError, match="did not keep"),
    ):
        await _set(hass, schedule(slot3={"batt": 65}, slot4={"batt": 65}))
    assert hass.states.get(f"number.{PREFIX}_tou_slot_3_soc").state == "85"
    assert hass.states.get(f"number.{PREFIX}_tou_slot_4_soc").state == "65"


async def test_write_failure_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    transport().fail = True
    with pytest.raises(HomeAssistantError, match="Could not change"):
        await _set(hass, schedule(slot3={"batt": 65}))


async def test_device_can_be_picked(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    device = next(
        d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if d.via_device_id is None
    )
    await _set(hass, schedule(slot3={"batt": 70}), device_id=device.id)
    assert transport().writes == [(0x010E, [70])]
    with pytest.raises(ServiceValidationError):
        await _set(hass, schedule(), device_id="nope")


async def test_family_without_tou_is_rejected(hass: HomeAssistant) -> None:
    await _setup(hass, device_type=5)
    with pytest.raises(ServiceValidationError, match="not supported"):
        await _set(hass, schedule())


async def test_left_out_fields_keep_changes_made_on_the_inverter(hass: HomeAssistant) -> None:
    await _setup(hass)
    fake = transport()
    # Changed on the inverter screen since the last settings read.
    fake.registers[0x010C] = 90
    fake.registers[0x00FC] = 1000
    await _set(hass, [{}, {}, {"batt": 65}, {}, {}, {}])
    assert fake.writes == [(0x010E, [65])]
    assert fake.registers[0x010C] == 90
    assert hass.states.get(f"number.{PREFIX}_tou_slot_1_soc").state == "90"
    assert hass.states.get(f"time.{PREFIX}_tou_slot_3_time").state == "10:00:00"


async def test_order_is_checked_against_the_inverter_now(hass: HomeAssistant) -> None:
    await _setup(hass)
    fake = transport()
    with pytest.raises(ServiceValidationError, match="increase"):
        await _set(hass, [{}, {"time": "10:00"}, {}, {}, {}, {}])
    assert fake.writes == []
    fake.registers[0x00FC] = 1100
    await _set(hass, [{}, {"time": "10:00"}, {}, {}, {}, {}])
    assert fake.writes == [(0x00FB, [1000])]


async def test_unloaded_inverter_cannot_be_changed(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError, match="Pick the device"):
        await _set(hass, schedule())


async def test_time_of_use_switch_carries_the_table(hass: HomeAssistant) -> None:
    await _setup(hass)
    state = hass.states.get(f"switch.{PREFIX}_time_of_use")
    schedule = state.attributes["schedule"]
    assert schedule[0] == {
        "time": "01:00", "power": 6000, "batt": 85,
        "grid_charge": True, "gen": False, "voltage": 49.0,
    }
    assert [slot["time"] for slot in schedule] == [s["time"] for s in CURRENT]
    await _set(hass, [{}, {}, {"batt": 65}, {}, {}, {}])
    schedule = hass.states.get(f"switch.{PREFIX}_time_of_use").attributes["schedule"]
    assert schedule[2]["batt"] == 65
    assert hass.states.get(f"switch.{PREFIX}_grid_charge").attributes.get("schedule") is None


async def test_card_is_served_and_loaded_with_the_frontend(hass: HomeAssistant) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.deye_local import FRONTEND_PATH

    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch("custom_components.deye_local.add_extra_js_url") as add_url:
        await _setup(hass)
    (paths,), _ = hass.http.async_register_static_paths.call_args
    assert paths[0].url_path == "/deye_local/frontend"
    assert (FRONTEND_PATH / "deye-local-tou-card.js").is_file()
    assert (FRONTEND_PATH / "tou-card-core.js").is_file()
    add_url.assert_called_once()
    assert add_url.call_args.args[1].startswith("/deye_local/frontend/deye-local-tou-card.js?v=")
