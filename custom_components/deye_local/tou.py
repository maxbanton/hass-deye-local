"""The time of use table, written as a whole like the inverter screen saves it.

A field left as None keeps the value the inverter holds at write time, so a
schedule built from slightly stale state does not undo a change made on the
inverter in the meantime.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .models import TOU_SLOTS, Control, Family, control_value, with_control_value


@dataclass(frozen=True)
class TouSlot:
    start: time | None = None
    power: int | None = None
    batt: int | None = None
    grid_charge: bool | None = None
    gen: bool | None = None
    voltage: float | None = None


def tou_control(family: Family, slot: int, field: str) -> Control | None:
    key = f"tou{slot + 1}_{field}"
    return next((c for c in family.controls if c.key == key), None)


def has_tou(family: Family) -> bool:
    return tou_control(family, 0, "time") is not None


def tou_columns(family: Family) -> list[range]:
    """One register run per column of the table (start times, power, ...)."""
    columns: list[range] = []
    for field in ("time", "power", "voltage", "soc", "grid_charge"):
        control = tou_control(family, 0, field)
        if control is not None:
            columns.append(range(control.register, control.register + TOU_SLOTS))
    return columns


def tou_span(family: Family) -> range:
    columns = tou_columns(family)
    return range(min(c.start for c in columns), max(c.stop for c in columns))


def tou_targets(family: Family, slots: list[TouSlot], current: dict[int, int]) -> dict[int, int]:
    """Register values for ``slots``, keeping bits the table does not cover."""
    targets: dict[int, int] = {}

    def put(slot: int, field: str, value: int | None) -> None:
        control = tou_control(family, slot, field)
        if control is None or value is None:
            return
        base = targets.get(control.register, current[control.register])
        targets[control.register] = with_control_value(control, base, value)

    def flag(value: bool | None) -> int | None:
        return None if value is None else int(value)

    for index, slot in enumerate(slots):
        if slot.start is not None:
            put(index, "time", slot.start.hour * 100 + slot.start.minute)
        put(index, "power", slot.power)
        put(index, "soc", slot.batt)
        put(index, "grid_charge", flag(slot.grid_charge))
        put(index, "generator_charge", flag(slot.gen))
        if slot.voltage is not None:
            control = tou_control(family, index, "voltage")
            if control is not None:
                put(index, "voltage", round(slot.voltage / control.scale))
    return targets


def tou_schedule(family: Family, regs: dict[int, int]) -> list[dict] | None:
    """The table in the action's field names, or None until it has been read."""

    def value(slot: int, field: str) -> float | None:
        control = tou_control(family, slot, field)
        raw = None if control is None else control_value(control, regs)
        return None if raw is None else round(raw * control.scale, 2)

    schedule = []
    for index in range(TOU_SLOTS):
        start, power, batt = (value(index, f) for f in ("time", "power", "soc"))
        if start is None or power is None or batt is None:
            return None
        hours, minutes = divmod(int(start), 100)
        slot = {
            "time": f"{hours:02d}:{minutes:02d}",
            "power": int(power),
            "batt": int(batt),
            "grid_charge": bool(value(index, "grid_charge")),
            "gen": bool(value(index, "generator_charge")),
        }
        voltage = value(index, "voltage")
        if voltage is not None:
            slot["voltage"] = voltage
        schedule.append(slot)
    return schedule


def tou_starts(family: Family, regs: dict[int, int]) -> list[int]:
    """Slot start times as HHMM, in slot order."""
    starts = []
    for index in range(TOU_SLOTS):
        control = tou_control(family, index, "time")
        if control is not None:
            starts.append(regs[control.register])
    return starts
