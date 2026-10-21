"""Actions of the Deye Local integration."""
from __future__ import annotations

from itertools import pairwise

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import DeyeLocalCoordinator
from .models import TOU_SLOTS, rated_power
from .tou import TouSlot, has_tou, tou_columns, tou_span, tou_starts, tou_targets

SERVICE_SET_TOU_SCHEDULE = "set_tou_schedule"
ATTR_DEVICE_ID = "device_id"
ATTR_SLOTS = "slots"

# Field names follow the inverter screen and the Deye Cloud integration's action
# of the same name, so one schedule works with either. Fields left out keep what
# the inverter holds when the write happens.
_SLOT_SCHEMA = vol.Schema(
    {
        vol.Optional("time"): cv.time,
        vol.Optional("power"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("batt"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional("grid_charge"): cv.boolean,
        vol.Optional("gen"): cv.boolean,
        vol.Optional("voltage"): vol.All(vol.Coerce(float), vol.Range(min=0, max=65)),
    }
)

_SET_TOU_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SLOTS): vol.All(
            cv.ensure_list, [_SLOT_SCHEMA], vol.Length(min=TOU_SLOTS, max=TOU_SLOTS)
        ),
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> DeyeLocalCoordinator:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if device_id := call.data.get(ATTR_DEVICE_ID):
        registry = dr.async_get(hass)
        entries = [
            entry for entry in entries
            if any(
                device.id == device_id
                for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
            )
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_device",
                translation_placeholders={"device_id": device_id},
            )
    elif len(entries) != 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="device_required")
    coordinator: DeyeLocalCoordinator = entries[0].runtime_data
    if not has_tou(coordinator.family):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="tou_not_supported",
            translation_placeholders={"model": coordinator.family.name},
        )
    return coordinator


def _slots(coordinator: DeyeLocalCoordinator, data: list[dict]) -> list[TouSlot]:
    slots = [
        TouSlot(
            start=slot["time"].replace(second=0, microsecond=0) if "time" in slot else None,
            power=slot.get("power"),
            batt=slot.get("batt"),
            grid_charge=slot.get("grid_charge"),
            gen=slot.get("gen"),
            voltage=slot.get("voltage"),
        )
        for slot in data
    ]
    limit = rated_power(coordinator.family, coordinator.data or {})
    for index, slot in enumerate(slots):
        if limit is not None and slot.power is not None and slot.power > limit:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_of_range",
                translation_placeholders={
                    "value": str(slot.power),
                    "name": f"TOU slot {index + 1} power",
                },
            )
    return slots


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def _set_tou_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        slots = _slots(coordinator, call.data[ATTR_SLOTS])
        family = coordinator.family

        def build(current: dict[int, int]) -> dict[int, int]:
            # Checked against what the inverter holds now, since slots may leave
            # some start times out.
            targets = tou_targets(family, slots, current)
            starts = tou_starts(family, {**current, **targets})
            if any(later <= earlier for earlier, later in pairwise(starts)):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="tou_schedule_order"
                )
            return targets

        await coordinator.async_write_registers(
            "Time of use schedule", tou_span(family), tou_columns(family), build
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_TOU_SCHEDULE, _set_tou_schedule, schema=_SET_TOU_SCHEMA
    )
