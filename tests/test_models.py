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
    load = next(s for s in THREE_PHASE.sensors if s.key == "load_power")
    assert load.kind is Kind.S32
    assert decode(load, {0x028D: 0xFFFF, 0x0293: 0xFFFF}) == -1


@pytest.mark.parametrize(
    "low,high,watts",
    [
        (0x000D, 0x0000, 13),
        (0xFFD3, 0xFFFF, -45),
        # The high word still holds the other sign near 0 W.
        (0xFFD3, 0x0000, -45),
        (0x000D, 0xFFFF, 13),
        (0x86A0, 0x0001, 100000),
        (0x7960, 0xFFFE, -100000),
    ],
)
def test_grid_power_trusts_the_sign_of_the_low_word(low, high, watts):
    grid = next(s for s in THREE_PHASE.sensors if s.key == "grid_power")
    assert decode(grid, {0x0271: low, 0x02B2: high}) == watts


def test_low_voltage_three_phase_has_the_single_phase_settings_lower():
    from custom_components.deye_local.models import SINGLE_PHASE

    low_voltage, high_voltage = family_for(0x0005), family_for(0x0006)
    single = {c.key: c for c in SINGLE_PHASE.controls}
    three = {c.key: c for c in low_voltage.controls}
    assert three.keys() == single.keys() | {"solar_sell", "max_solar_power"}
    assert all(three[k].register == single[k].register - 0x66 for k in single)
    assert three["time_of_use"].register == 0x0092
    assert three["tou1_soc"].register == 0x00A6
    assert three["max_charge_current"].register == 0x006C
    shaving = three["grid_peak_shaving"]
    assert (shaving.register, shaving.mask, shaving.write_bits) == (0x00B2, 0x0010, 0x0020)
    assert three["grid_charge_current"].maximum == 350
    assert high_voltage.controls == ()
    assert high_voltage.key == low_voltage.key
    assert {s.key for s in high_voltage.sensors} == {s.key for s in low_voltage.sensors} - {
        "rated_power"
    }
    assert all(c.enabled for c in low_voltage.controls)
    assert three["solar_sell"].register == 0x0091
    assert three["max_solar_power"].register == 0x0154


# Read from a SUN-10K-SG04LP3-EU on 2026-11-18, a minute apart from the Deye
# Cloud values in the comments.
THREE_PHASE_PER_PHASE = {
    0x0262: 73, 0x0263: 106, 0x0264: 535, 0x0265: 93, 0x0266: 111, 0x0267: 166,
    0x0268: 4, 0x0269: 3, 0x026A: 5, 0x026B: 12, 0x02C4: 0,
    0x0273: 2349, 0x0274: 2337, 0x0275: 2346,
    0x0276: 50, 0x0277: 90, 0x0278: 530,
    0x0279: 157, 0x027A: 243, 0x027B: 1264, 0x027C: 1664, 0x02B6: 0,
    0x0280: 14, 0x0281: 17, 0x0282: 24, 0x0283: 55, 0x02BB: 0,
    0x0284: 2335, 0x0285: 2340, 0x0286: 2332,
    0x028A: 161, 0x028B: 243, 0x028C: 1265, 0x028D: 1669, 0x0293: 0,
}


def test_three_phase_per_phase_readings():
    values = {
        s.key: decode(s, THREE_PHASE_PER_PHASE)
        for s in THREE_PHASE.sensors
        if all(r in THREE_PHASE_PER_PHASE for r in s.registers)
    }
    # Cloud: grid 0.74 A, inverter 235.1 V 0.50 A 161 W, UPS 233.5 V, CT 2 W.
    assert [values[f"inverter_grid_port_l{n}_current"] for n in (1, 2, 3)] == [0.73, 1.06, 5.35]
    assert [values[f"external_ct_l{n}_current"] for n in (1, 2, 3)] == [0.93, 1.11, 1.66]
    assert [values[f"inverter_l{n}_voltage"] for n in (1, 2, 3)] == [234.9, 233.7, 234.6]
    assert [values[f"inverter_l{n}_current"] for n in (1, 2, 3)] == [0.5, 0.9, 5.3]
    assert [values[f"load_l{n}_voltage"] for n in (1, 2, 3)] == [233.5, 234.0, 233.2]
    for part in ("external_ct", "inverter", "ups", "load"):
        phases = [values[f"{part}_l{n}_power"] for n in (1, 2, 3)]
        assert sum(phases) == values[f"{part}_power"], part


def test_three_phase_per_phase_sensors_are_enabled_by_default():
    parts = ("inverter_grid_port_l{}_current", "external_ct_l{}_current", "external_ct_l{}_power",
             "inverter_l{}_voltage", "inverter_l{}_current", "inverter_l{}_power",
             "ups_l{}_power", "load_l{}_voltage", "load_l{}_power")
    keys = {part.format(n) for part in parts for n in (1, 2, 3)}
    sensors = {s.key: s for s in THREE_PHASE.sensors}
    assert keys <= sensors.keys()
    assert all(sensors[key].enabled for key in keys)


@pytest.mark.parametrize(
    "code,key,support",
    [
        (0x0003, "single_phase_hybrid", Support.SUPPORTED),
        (0x0300, "single_phase_hybrid", Support.SUPPORTED),
        (0x0005, "three_phase_hybrid", Support.SUPPORTED),
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
        THREE_PHASE_HV,
        control_value,
        rated_power,
    )

    assert rated_power(THREE_PHASE_HV, SNAPSHOT) is None
    # Read from a SUN-10K-SG05LP3-EU-SM2.
    assert rated_power(THREE_PHASE, {0x0014: 34464, 0x0015: 1}) == 10000
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


# Read from the same SUN-10K-SG04LP3-EU, and from a SUN-12K-SG05LP3-EU, whose
# Deye Cloud pages showed 10 kW and 12 kW.
THREE_PHASE_10K = {
    0x0014: 34464, 0x0015: 1, 0x026D: 65476, 0x0200: 9, 0x0201: 0,
    0x0218: 0, 0x0219: 0, 0x021A: 0, 0x021B: 0, 0x0228: 5, 0x029B: 0, 0x029F: 0,
}
THREE_PHASE_12K = {0x0014: 54464, 0x0015: 1, 0x026D: 998, 0x0228: 5}


def test_three_phase_status_readings():
    values = {
        s.key: decode(s, THREE_PHASE_10K)
        for s in THREE_PHASE.sensors
        if all(r in THREE_PHASE_10K for r in s.registers)
    }
    assert values["rated_power"] == 10000
    assert values["grid_power_factor"] == -6.0
    assert values["total_generator_runtime"] == 0.9
    assert values["today_generator_runtime"] == 0
    assert values["generator_power"] == 0
    sensors = {s.key: s for s in THREE_PHASE.sensors}
    assert decode(sensors["rated_power"], THREE_PHASE_12K) == 12000
    assert decode(sensors["grid_power_factor"], THREE_PHASE_12K) == 99.8


def test_fixed_values_are_read_with_the_settings():
    fixed = {r for s in THREE_PHASE.sensors if s.setting for r in s.registers}
    assert fixed == {0x0014, 0x0015}
    assert fixed <= THREE_PHASE.setting_registers
    assert not fixed & THREE_PHASE.registers
    assert 0x0228 in THREE_PHASE.registers


def test_single_phase_rated_power():
    from .snapshot import SETTINGS

    rated = next(s for s in SINGLE_PHASE.sensors if s.key == "rated_power")
    assert decode(rated, SETTINGS) == 6000
