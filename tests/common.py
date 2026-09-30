"""Shared test doubles."""
from __future__ import annotations

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from custom_components.deye_local.const import SERVICE_UUID
from custom_components.deye_local.transport import RegisterUnavailable, TransportError

from .snapshot import BATTERIES, SETTINGS, SNAPSHOT

ADDRESS = "88:A6:8D:2C:4F:15"
NAME = "D26109249480"


def service_info(address: str = ADDRESS, name: str = NAME) -> BluetoothServiceInfoBleak:
    try:
        device = BLEDevice(address, name, None)
    except TypeError:  # bleak before 1.0 still required rssi
        device = BLEDevice(address, name, None, -60)
    advertisement = AdvertisementData(
        local_name=name,
        manufacturer_data={},
        service_data={},
        service_uuids=[SERVICE_UUID],
        tx_power=None,
        rssi=-60,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[SERVICE_UUID],
        source="local",
        device=device,
        advertisement=advertisement,
        connectable=True,
        time=0,
        tx_power=None,
    )


class FakeTransport:
    """Serves registers from a snapshot; unknown registers read as zero."""

    instances: list[FakeTransport] = []

    def __init__(self, device, registers: dict[int, int] | None = None) -> None:
        self.device = device
        if registers is None:
            registers = {**SNAPSHOT, **SETTINGS, **BATTERIES}
        self.registers = dict(registers)
        self.unavailable_from: int | None = None
        self.unavailable_blocks: set[int] = set()
        self.busy_from: int | None = None
        self.fail = False
        self.connected = False
        self.connects = 0
        self.disconnects = 0
        self.reads: list[tuple[int, int]] = []
        self.writes: list[tuple[int, list[int]]] = []
        # Registers the inverter acknowledges but does not change.
        self.ignored_writes: set[int] = set()
        self.logger_type = "21511,21511"
        FakeTransport.instances.append(self)

    def set_device(self, device) -> None:
        self.device = device

    async def async_connect(self) -> None:
        if self.fail:
            raise TransportError("logger not answering")
        if not self.connected:
            self.connects += 1
        self.connected = True

    async def async_read(self, start: int, count: int) -> list[int]:
        if self.fail:
            raise TransportError("logger not answering")
        self.reads.append((start, count))
        if self.unavailable_from is not None and start >= self.unavailable_from:
            raise RegisterUnavailable("illegal data address")
        if any(first <= start < first + 0x26 for first in self.unavailable_blocks):
            raise RegisterUnavailable("illegal data address")
        if self.busy_from is not None and start >= self.busy_from:
            raise TransportError("inverter rejected the read (exception 6)")
        return [self.registers.get(start + i, 0) for i in range(count)]

    async def async_write(self, start: int, values: list[int]) -> None:
        if self.fail:
            raise TransportError("logger not answering")
        self.writes.append((start, list(values)))
        for offset, value in enumerate(values):
            if start + offset not in self.ignored_writes:
                self.registers[start + offset] = value

    async def async_disconnect(self) -> None:
        if self.connected:
            self.disconnects += 1
        self.connected = False

    async def async_close(self) -> None:
        self.closed = True
        await self.async_disconnect()
