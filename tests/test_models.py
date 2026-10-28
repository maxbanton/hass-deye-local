"""Register map tests, checked against a real inverter snapshot and the Deye Cloud."""
from __future__ import annotations

import pytest

from custom_components.deye_local.const import MAX_BLOCK
from custom_components.deye_local.models import (
    FAMILIES,
    SINGLE_PHASE,
    THREE_PHASE,
    Coarse,
    Kind,
    Support,
    decode,
    describe_codes,
    family_for,
    has_string,
)
from custom_components.deye_local.protocol import plan_blocks

from .snapshot import SNAPSHOT, SNAPSHOT_10K

SENSORS = {sensor.key: sensor for sensor in SINGLE_PHASE.sensors}


def value(key):
    return decode(SENSORS[key], SNAPSHOT)


@pytest.mark.parametrize(
    "key,expected",
    [
        # Values the Deye Cloud reported for the same moment.
        ("battery_soc", 86),
        ("battery_temperature", 18.0),
        ("dc_temperature", 39.1),
        ("ac_temperature", 33.2),
        ("total_battery_charge", 48.8),
        ("total_battery_discharge", 19.4),
        ("today_grid_import", 2.7),
        # Values without a cloud counterpart, decoded from the same snapshot.
        ("battery_voltage", 53.55),
        ("grid_voltage", 227.4),
        ("grid_frequency", 50.01),
        ("total_grid_import", 269.1),
        ("total_load", 260.6),
    ],
)
def test_single_phase_matches_the_cloud(key, expected):
    assert value(key) == pytest.approx(expected)


def test_signed_values_decode_negative():
    assert value("battery_power") == -44
    assert value("battery_current") == pytest.approx(-0.84)
    assert value("inverter_power") == -41


def test_status_values():
    assert value("device_state") == "normal"
    assert value("inverter_clock") == "2026-09-30 10:35:56"
    assert value("device_type") == "Single phase hybrid"


def test_fault_codes_use_deye_numbering():
    fault = SENSORS["fault"]
    regs = dict(SNAPSHOT)
    regs.update({0x0067: 0, 0x0068: 0, 0x0069: 0, 0x006A: 0})
    assert decode(fault, regs) == "OK"
    regs[0x0067] = 1 << 12  # the fault shown as F13 on the inverter display
    assert decode(fault, regs) == "F13"
    assert describe_codes(fault, regs) == {"F13": "Working mode changed"}


def test_missing_registers_decode_to_none():
    assert decode(SENSORS["bms_soc"], SNAPSHOT) is None


def test_32_bit_values_are_low_word_first():
    sensor = SENSORS["total_battery_charge"]
    assert decode(sensor, {0x0048: 0x0001, 0x0049: 0x0001}) == pytest.approx(6553.7)


def test_signed_32_bit():
    grid = next(s for s in THREE_PHASE.sensors if s.key == "grid_power")
    assert grid.kind is Kind.S32
    assert decode(grid, {0x0271: 0xFFFF, 0x02B2: 0xFFFF}) == -1


@pytest.mark.parametrize(
    "code,key,support",
    [
        (0x0003, "single_phase_hybrid", Support.SUPPORTED),
        (0x0300, "single_phase_hybrid", Support.SUPPORTED),
        (0x0005, "three_phase_hybrid", Support.EXPERIMENTAL),
        (0x0006, "three_phase_hybrid", Support.EXPERIMENTAL),
        (0x0002, "unsupported", Support.UNSUPPORTED),
        (0x1234, "unsupported", Support.UNSUPPORTED),
    ],
)
def test_family_detection(code, key, support):
    family = family_for(code)
    assert (family.key, family.support) == (key, support)


def test_unknown_family_still_exposes_its_identity():
    family = family_for(0x1234)
    assert {s.key for s in family.sensors} == {"device_type", "protocol_version"}
    assert family.name == "Unknown type 0x1234"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.key)
def test_every_family_is_readable(family):
    keys = [s.key for s in family.sensors]
    assert len(keys) == len(set(keys))
    blocks = plan_blocks(family.registers, MAX_BLOCK)
    assert all(count <= MAX_BLOCK for _, count in blocks)
    covered = {start + i for start, count in blocks for i in range(count)}
    assert family.registers <= covered


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.key)
def test_energy_counters_feed_the_energy_dashboard(family):
    for sensor in family.sensors:
        if sensor.unit == "kWh":
            assert sensor.state_class == "total_increasing", sensor.key


def test_codes_need_their_registers():
    from custom_components.deye_local.models import SINGLE_PHASE, Kind, describe_codes

    fault = next(s for s in SINGLE_PHASE.sensors if s.kind is Kind.FAULT)
    assert describe_codes(fault, {}) == {}
    plain = next(s for s in SINGLE_PHASE.sensors if s.kind not in (Kind.FAULT, Kind.ALARM))
    assert describe_codes(plain, SNAPSHOT) == {}


def test_alarm_codes_use_deye_numbering():
    from custom_components.deye_local.models import SINGLE_PHASE, Kind, describe_codes

    alarm = next(s for s in SINGLE_PHASE.sensors if s.kind is Kind.ALARM)
    regs = dict.fromkeys(alarm.registers, 0)
    regs[alarm.registers[0]] = 0b10
    assert list(describe_codes(alarm, regs)) == ["W02"]


def test_rated_power_needs_the_family_and_its_registers():
    from custom_components.deye_local.models import (
        SINGLE_PHASE,
        THREE_PHASE,
        control_value,
        rated_power,
    )

    assert rated_power(THREE_PHASE, SNAPSHOT) is None
    assert rated_power(SINGLE_PHASE, {}) is None
    assert control_value(SINGLE_PHASE.controls[0], {}) is None


def _coarse(regs):
    return {group for group, check in SINGLE_PHASE.unit_checks if check(regs)}


def test_coarse_unit_is_detected_and_scaled():
    assert {group: check(SNAPSHOT_10K) for group, check in SINGLE_PHASE.unit_checks} == {
        Coarse.POWER: True,
        Coarse.BATTERY_CURRENT: True,
    }
    coarse = _coarse(SNAPSHOT_10K)
    assert decode(SENSORS["grid_power"], SNAPSHOT_10K, coarse) == 3850
    assert decode(SENSORS["external_ct_power"], SNAPSHOT_10K, coarse) == 3850
    assert decode(SENSORS["load_power"], SNAPSHOT_10K, coarse) == 2210
    assert decode(SENSORS["battery_current"], SNAPSHOT_10K, coarse) == pytest.approx(-25.8)
    assert decode(SENSORS["inverter_power"], SNAPSHOT_10K, coarse) == -1636
    assert decode(SENSORS["battery_power"], SNAPSHOT_10K, coarse) == -1407


def test_documented_unit_is_detected():
    # A SUN-6K discharging into the house: 1.8 kW load, 20.9 A out of the battery.
    regs = {0x00A9: 300, 0x00AF: 1500, 0x00B2: 1800, 0x00B7: 5300, 0x00BE: 1110,
            0x00BF: 2090}
    assert [check(regs) for _, check in SINGLE_PHASE.unit_checks] == [False, False]


@pytest.mark.parametrize(
    "regs",
    [
        # Too little inverter power and battery current to tell.
        SNAPSHOT,
        # Readings that fit neither unit.
        {0x00A9: 1000, 0x00AF: 1000, 0x00B2: 1000, 0x00B7: 5000, 0x00BE: 1000,
         0x00BF: 500},
        # Missing registers.
        {},
        {0x00B7: 0, 0x00BE: 1000, 0x00BF: 2000},
    ],
)
def test_unit_checks_abstain(regs):
    assert [check(regs) for _, check in SINGLE_PHASE.unit_checks] == [None, None]


def test_pv_strings_follow_the_mppt_count():
    pv3 = SENSORS["pv3_power"]
    assert not has_string(SINGLE_PHASE, pv3, {0x0012: 0x0201})
    assert not has_string(SINGLE_PHASE, pv3, {})
    assert has_string(SINGLE_PHASE, pv3, SNAPSHOT_10K)
    assert not has_string(SINGLE_PHASE, SENSORS["pv4_power"], SNAPSHOT_10K)
    assert has_string(SINGLE_PHASE, SENSORS["pv1_power"], {})
    assert decode(SENSORS["pv3_voltage"], SNAPSHOT_10K) == pytest.approx(3.8)
