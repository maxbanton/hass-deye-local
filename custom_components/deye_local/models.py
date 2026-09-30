"""Inverter families and their register maps.

Register 0 of every Deye inverter reports its family, and each family has its
own layout. Multi-register values are stored low word first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

REG_DEVICE_TYPE = 0x0000
REG_PROTOCOL = 0x0002
REG_SERIAL = tuple(range(0x0003, 0x0008))
IDENTITY_BLOCK = (0x0000, 8)


class Support(StrEnum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


class Kind(StrEnum):
    U16 = "u16"
    S16 = "s16"
    U32 = "u32"
    S32 = "s32"
    STATE = "state"
    ALARM = "alarm"
    FAULT = "fault"
    CLOCK = "clock"
    DEVICE_TYPE = "device_type"
    DIFFERENCE = "difference"


DEVICE_STATES = ["standby", "self_test", "normal", "alarm", "fault"]

# Deye displays fault bit n as code F(n+1).
FAULT_NAMES = {
    6: "DC/DC soft start failure",
    9: "Auxiliary power supply failure",
    12: "Working mode changed",
    17: "AC over-current",
    18: "Tz integration fault",
    19: "DC over-current",
    22: "AC current leakage",
    63: "Temperature too high",
}
ALARM_NAMES = {
    1: "Fan failure",
    2: "Grid phase failure",
    3: "Meter communication failure",
    30: "Battery loss",
    31: "Parallel communication quality",
}


@dataclass(frozen=True, kw_only=True)
class RegisterSensor:
    key: str
    name: str
    registers: tuple[int, ...]
    kind: Kind = Kind.U16
    scale: float = 1
    offset: int = 0
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    precision: int | None = None
    enabled: bool = True
    diagnostic: bool = False


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    codes: frozenset[int]
    support: Support
    sensors: tuple[RegisterSensor, ...] = field(default=())
    has_battery_modules: bool = False

    @property
    def registers(self) -> set[int]:
        return {reg for sensor in self.sensors for reg in sensor.registers}


def _words(regs: dict[int, int], addresses: tuple[int, ...]) -> int:
    value = 0
    for index, address in enumerate(addresses):
        value |= regs[address] << (16 * index)
    return value


def _bits(value: int) -> list[int]:
    return [bit for bit in range(value.bit_length()) if value >> bit & 1]


def decode(sensor: RegisterSensor, regs: dict[int, int]) -> Any:
    try:
        raw = _words(regs, sensor.registers)
    except KeyError:
        return None
    width = 16 * len(sensor.registers)
    match sensor.kind:
        case Kind.S16 | Kind.S32:
            if raw >= 1 << (width - 1):
                raw -= 1 << width
        case Kind.STATE:
            return DEVICE_STATES[raw] if raw < len(DEVICE_STATES) else None
        case Kind.ALARM:
            return ", ".join(f"W{bit + 1:02d}" for bit in _bits(raw)) or "OK"
        case Kind.FAULT:
            return ", ".join(f"F{bit + 1:02d}" for bit in _bits(raw)) or "OK"
        case Kind.DEVICE_TYPE:
            return family_for(raw).name
        case Kind.DIFFERENCE:
            first, second = (regs[r] for r in sensor.registers)
            return round((first - second) * sensor.scale, sensor.precision or 0)
        case Kind.CLOCK:
            a, b, c = (regs[r] for r in sensor.registers)
            return (
                f"20{a >> 8:02d}-{a & 0xFF:02d}-{b >> 8:02d} "
                f"{b & 0xFF:02d}:{c >> 8:02d}:{c & 0xFF:02d}"
            )
    value = (raw - sensor.offset) * sensor.scale
    if sensor.precision is not None:
        return round(value, sensor.precision)
    return value


def describe_codes(sensor: RegisterSensor, regs: dict[int, int]) -> dict[str, str]:
    try:
        raw = _words(regs, sensor.registers)
    except KeyError:
        return {}
    if sensor.kind is Kind.FAULT:
        return {f"F{b + 1:02d}": FAULT_NAMES.get(b, "Unknown") for b in _bits(raw)}
    if sensor.kind is Kind.ALARM:
        return {f"W{b + 1:02d}": ALARM_NAMES.get(b, "Unknown") for b in _bits(raw)}
    return {}


P = SensorDeviceClass.POWER
E = SensorDeviceClass.ENERGY
V = SensorDeviceClass.VOLTAGE
A = SensorDeviceClass.CURRENT
T = SensorDeviceClass.TEMPERATURE
F = SensorDeviceClass.FREQUENCY
W = UnitOfPower.WATT
KWH = UnitOfEnergy.KILO_WATT_HOUR
VOLT = UnitOfElectricPotential.VOLT
AMP = UnitOfElectricCurrent.AMPERE
HZ = UnitOfFrequency.HERTZ
DEG = UnitOfTemperature.CELSIUS
TOTAL = SensorStateClass.TOTAL_INCREASING


def power(key, name, *regs, kind=Kind.S16, **kw) -> RegisterSensor:
    return RegisterSensor(key=key, name=name, registers=regs, kind=kind, unit=W,
                          device_class=P, **kw)


def energy(key, name, *regs, **kw) -> RegisterSensor:
    kind = Kind.U32 if len(regs) > 1 else Kind.U16
    return RegisterSensor(key=key, name=name, registers=regs, kind=kind, scale=0.1,
                          unit=KWH, device_class=E, state_class=TOTAL, precision=1, **kw)


def volts(key, name, reg, scale=0.1, **kw) -> RegisterSensor:
    return RegisterSensor(key=key, name=name, registers=(reg,), scale=scale, unit=VOLT,
                          device_class=V, precision=2 if scale < 0.1 else 1, **kw)


def amps(key, name, reg, scale=0.01, kind=Kind.S16, **kw) -> RegisterSensor:
    return RegisterSensor(key=key, name=name, registers=(reg,), kind=kind, scale=scale,
                          unit=AMP, device_class=A, precision=2 if scale < 0.1 else 1, **kw)


def temperature(key, name, reg, **kw) -> RegisterSensor:
    return RegisterSensor(key=key, name=name, registers=(reg,), kind=Kind.S16, scale=0.1,
                          offset=1000, unit=DEG, device_class=T, precision=1, **kw)


def hertz(key, name, reg, **kw) -> RegisterSensor:
    return RegisterSensor(key=key, name=name, registers=(reg,), scale=0.01, unit=HZ,
                          device_class=F, precision=2, **kw)


def status(state: int, alarm: tuple[int, ...], fault: tuple[int, ...],
           clock: tuple[int, ...]) -> tuple[RegisterSensor, ...]:
    return (
        RegisterSensor(key="device_state", name="Device state", registers=(state,),
                       kind=Kind.STATE, device_class=SensorDeviceClass.ENUM, state_class=None),
        RegisterSensor(key="alarm", name="Alarm", registers=alarm, kind=Kind.ALARM,
                       state_class=None),
        RegisterSensor(key="fault", name="Fault", registers=fault, kind=Kind.FAULT,
                       state_class=None),
        RegisterSensor(key="inverter_clock", name="Inverter clock", registers=clock,
                       kind=Kind.CLOCK, state_class=None, enabled=False, diagnostic=True),
    )


def bms(base: int, *, current_scale: float = 1) -> tuple[RegisterSensor, ...]:
    return (
        volts("bms_charge_voltage", "BMS charge voltage", base, scale=0.01),
        volts("bms_discharge_voltage", "BMS discharge voltage", base + 1, scale=0.01),
        amps("bms_charge_current_limit", "BMS charge current limit", base + 2, scale=1,
             kind=Kind.U16),
        amps("bms_discharge_current_limit", "BMS discharge current limit", base + 3, scale=1,
             kind=Kind.U16),
        RegisterSensor(key="bms_soc", name="BMS SOC", registers=(base + 4,), unit=PERCENTAGE,
                       device_class=SensorDeviceClass.BATTERY),
        volts("bms_voltage", "BMS voltage", base + 5, scale=0.01),
        amps("bms_current", "BMS current", base + 6, scale=current_scale),
        amps("bms_max_charge_current", "BMS max charge current", base + 8, scale=1,
             kind=Kind.U16, enabled=False),
        amps("bms_max_discharge_current", "BMS max discharge current", base + 9, scale=1,
             kind=Kind.U16, enabled=False),
    )


IDENTITY = (
    RegisterSensor(key="device_type", name="Device type", registers=(REG_DEVICE_TYPE,),
                   kind=Kind.DEVICE_TYPE, state_class=None, diagnostic=True),
    RegisterSensor(key="protocol_version", name="Protocol version", registers=(REG_PROTOCOL,),
                   state_class=None, diagnostic=True, enabled=False),
)


# Per-module battery blocks, one every BATTERY_STRIDE registers. Offsets are
# relative to the start of a block; the first eight registers hold the serial.
BATTERY_BASE = 0x2730
BATTERY_STRIDE = 0x26
MAX_BATTERIES = 4
BATTERY_SERIAL_LENGTH = 8


def battery_serial_block(index: int) -> tuple[int, int]:
    return BATTERY_BASE + index * BATTERY_STRIDE, BATTERY_SERIAL_LENGTH


@cache
def battery_sensors(index: int) -> tuple[RegisterSensor, ...]:
    base = BATTERY_BASE + index * BATTERY_STRIDE
    mv = UnitOfElectricPotential.MILLIVOLT
    return (
        RegisterSensor(key="soc", name="SOC", registers=(base + 15,), scale=0.1,
                       unit=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, precision=1),
        volts("voltage", "Voltage", base + 8),
        amps("current", "Current", base + 9, scale=0.1),
        temperature("temperature", "Temperature", base + 10),
        RegisterSensor(key="max_cell_voltage", name="Max cell voltage", registers=(base + 22,),
                       scale=0.001, unit=VOLT, device_class=V, precision=3),
        RegisterSensor(key="min_cell_voltage", name="Min cell voltage", registers=(base + 23,),
                       scale=0.001, unit=VOLT, device_class=V, precision=3),
        RegisterSensor(key="cell_voltage_difference", name="Cell voltage difference",
                       registers=(base + 22, base + 23), kind=Kind.DIFFERENCE, unit=mv,
                       device_class=V, precision=0),
        RegisterSensor(key="soh", name="State of health", registers=(base + 16,), scale=0.1,
                       unit=PERCENTAGE, precision=1),
        RegisterSensor(key="cycles", name="Cycles", registers=(base + 24,), state_class=TOTAL),
        RegisterSensor(key="capacity", name="Capacity", registers=(base + 18,), scale=0.1,
                       unit="Ah", precision=1, enabled=False),
        temperature("max_cell_temperature", "Max cell temperature", base + 11, enabled=False),
        temperature("min_cell_temperature", "Min cell temperature", base + 12, enabled=False),
        temperature("mos_temperature", "MOS temperature", base + 13, enabled=False),
    )


def battery_sensor(index: int, key: str) -> RegisterSensor:
    return next(sensor for sensor in battery_sensors(index) if sensor.key == key)


# SUN-*K-SG0*LP1
SINGLE_PHASE = Family(
    key="single_phase_hybrid",
    name="Single phase hybrid",
    codes=frozenset({0x0003, 0x0300}),
    support=Support.SUPPORTED,
    has_battery_modules=True,
    sensors=(
        *IDENTITY,
        *status(0x003B, (0x0065, 0x0066), (0x0067, 0x0068, 0x0069, 0x006A),
                (0x0016, 0x0017, 0x0018)),
        RegisterSensor(key="battery_soc", name="Battery SOC",
                       registers=(0x00B8,),
                       unit=PERCENTAGE, device_class=SensorDeviceClass.BATTERY),
        volts("battery_voltage", "Battery voltage", 0x00B7, scale=0.01),
        amps("battery_current", "Battery current", 0x00BF),
        power("battery_power", "Battery power", 0x00BE),
        temperature("battery_temperature", "Battery temperature", 0x00B6),
        volts("grid_voltage", "Grid voltage", 0x0096),
        hertz("grid_frequency", "Grid frequency", 0x004F),
        power("grid_power", "Grid power", 0x00A9),
        amps("grid_current", "Grid current", 0x00A0, enabled=False),
        power("external_ct_power", "External CT power", 0x00AC, enabled=False),
        volts("output_voltage", "Output voltage", 0x009C, enabled=False),
        hertz("output_frequency", "Output frequency", 0x00C1, enabled=False),
        power("inverter_power", "Inverter power", 0x00AF),
        power("load_power", "Load power", 0x00B2),
        hertz("load_frequency", "Load frequency", 0x00C0, enabled=False),
        volts("load_voltage", "Load voltage", 0x009D, enabled=False),
        power("pv1_power", "PV1 power", 0x00BA, kind=Kind.U16),
        power("pv2_power", "PV2 power", 0x00BB, kind=Kind.U16),
        volts("pv1_voltage", "PV1 voltage", 0x006D, enabled=False),
        amps("pv1_current", "PV1 current", 0x006E, scale=0.1, kind=Kind.U16, enabled=False),
        volts("pv2_voltage", "PV2 voltage", 0x006F, enabled=False),
        amps("pv2_current", "PV2 current", 0x0070, scale=0.1, kind=Kind.U16, enabled=False),
        power("generator_power", "Generator power", 0x00A6, kind=Kind.U16, enabled=False),
        temperature("dc_temperature", "DC temperature", 0x005A),
        temperature("ac_temperature", "AC temperature", 0x005B),
        energy("today_battery_charge", "Today battery charge", 0x0046),
        energy("today_battery_discharge", "Today battery discharge", 0x0047),
        energy("total_battery_charge", "Total battery charge", 0x0048, 0x0049),
        energy("total_battery_discharge", "Total battery discharge", 0x004A, 0x004B),
        energy("today_grid_import", "Today grid import", 0x004C),
        energy("today_grid_export", "Today grid export", 0x004D),
        energy("total_grid_import", "Total grid import", 0x004E, 0x0050),
        energy("total_grid_export", "Total grid export", 0x0051, 0x0052),
        energy("today_load", "Today load consumption", 0x0054),
        energy("total_load", "Total load consumption", 0x0055, 0x0056),
        energy("today_production", "Today PV production", 0x006C),
        energy("total_production", "Total PV production", 0x0060, 0x0061),
        *bms(0x0138),
    ),
)


# SUN-*K-SG0*LP3, SUN-*K-SG0*HP3
THREE_PHASE = Family(
    key="three_phase_hybrid",
    name="Three phase hybrid",
    codes=frozenset({0x0005, 0x0500, 0x0006}),
    support=Support.EXPERIMENTAL,
    has_battery_modules=True,
    sensors=(
        *IDENTITY,
        *status(0x01F4, (0x0229, 0x022A), (0x022B, 0x022C, 0x022D, 0x022E),
                (0x003E, 0x003F, 0x0040)),
        RegisterSensor(key="battery_soc", name="Battery SOC",
                       registers=(0x024C,),
                       unit=PERCENTAGE, device_class=SensorDeviceClass.BATTERY),
        volts("battery_voltage", "Battery voltage", 0x024B, scale=0.01),
        amps("battery_current", "Battery current", 0x024F),
        power("battery_power", "Battery power", 0x024E),
        temperature("battery_temperature", "Battery temperature", 0x024A),
        volts("grid_l1_voltage", "Grid L1 voltage", 0x0256),
        volts("grid_l2_voltage", "Grid L2 voltage", 0x0257),
        volts("grid_l3_voltage", "Grid L3 voltage", 0x0258),
        hertz("grid_frequency", "Grid frequency", 0x0261),
        power("grid_power", "Grid power", 0x0271, 0x02B2, kind=Kind.S32),
        power("grid_l1_power", "Grid L1 power", 0x026E, 0x02AF, kind=Kind.S32, enabled=False),
        power("grid_l2_power", "Grid L2 power", 0x026F, 0x02B0, kind=Kind.S32, enabled=False),
        power("grid_l3_power", "Grid L3 power", 0x0270, 0x02B1, kind=Kind.S32, enabled=False),
        power("external_ct_power", "External CT power", 0x026B, 0x02C4, kind=Kind.S32,
              enabled=False),
        power("inverter_power", "Inverter power", 0x027C, 0x02B6, kind=Kind.S32),
        power("ups_power", "UPS power", 0x0283, 0x02BB, kind=Kind.S32),
        power("load_power", "Load power", 0x028D, 0x0293, kind=Kind.S32),
        hertz("load_frequency", "Load frequency", 0x028F, enabled=False),
        power("pv1_power", "PV1 power", 0x02A0, kind=Kind.U16),
        power("pv2_power", "PV2 power", 0x02A1, kind=Kind.U16),
        power("pv3_power", "PV3 power", 0x02A2, kind=Kind.U16, enabled=False),
        power("pv4_power", "PV4 power", 0x02A3, kind=Kind.U16, enabled=False),
        volts("pv1_voltage", "PV1 voltage", 0x02A4, enabled=False),
        amps("pv1_current", "PV1 current", 0x02A5, scale=0.1, kind=Kind.U16, enabled=False),
        volts("pv2_voltage", "PV2 voltage", 0x02A6, enabled=False),
        amps("pv2_current", "PV2 current", 0x02A7, scale=0.1, kind=Kind.U16, enabled=False),
        temperature("dc_temperature", "DC temperature", 0x021C),
        temperature("ac_temperature", "AC temperature", 0x021D),
        energy("today_battery_charge", "Today battery charge", 0x0202),
        energy("today_battery_discharge", "Today battery discharge", 0x0203),
        energy("total_battery_charge", "Total battery charge", 0x0204, 0x0205),
        energy("total_battery_discharge", "Total battery discharge", 0x0206, 0x0207),
        energy("today_grid_import", "Today grid import", 0x0208),
        energy("today_grid_export", "Today grid export", 0x0209),
        energy("total_grid_import", "Total grid import", 0x020A, 0x020B),
        energy("total_grid_export", "Total grid export", 0x020C, 0x020D),
        energy("today_load", "Today load consumption", 0x020E),
        energy("total_load", "Total load consumption", 0x020F, 0x0210),
        energy("today_production", "Today PV production", 0x0211),
        energy("total_production", "Total PV production", 0x0216, 0x0217),
        *bms(0x00D2),
    ),
)


KNOWN_UNSUPPORTED = {
    0x0002: "String inverter",
    0x0200: "String inverter",
    0x0004: "Microinverter",
    0x0400: "Microinverter",
    0x0007: "HV three phase inverter",
    0x0600: "HV three phase inverter",
    0x0008: "HV three phase inverter",
    0x0601: "HV three phase inverter",
    0x0103: "Off grid inverter",
    0x0104: "Energy storage system",
}

FAMILIES = (SINGLE_PHASE, THREE_PHASE)


def family_for(device_type: int) -> Family:
    for family in FAMILIES:
        if device_type in family.codes:
            return family
    name = KNOWN_UNSUPPORTED.get(device_type, f"Unknown type {device_type:#06x}")
    return Family(key="unsupported", name=name, codes=frozenset({device_type}),
                  support=Support.UNSUPPORTED, sensors=IDENTITY)
