"""BLE session with the WiBLE data logger.

The logger replies to every command on one notify characteristic, so commands
are serialised with a lock, and notifications that arrive while no command is
waiting are dropped rather than mistaken for the next reply.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol
from .const import COMMAND_CHAR, NOTIFY_CHAR, REPLY_TIMEOUT

_LOGGER = logging.getLogger(__name__)

SUBSCRIBE_TIMEOUT = 10.0


class TransportError(Exception):
    """The logger could not be reached or did not answer."""


class RegisterUnavailable(TransportError):
    """The inverter reports that the requested registers do not exist."""


class DeyeTransport:
    def __init__(self, device: BLEDevice) -> None:
        self._device = device
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._buffer = ""
        self._received = asyncio.Event()
        self._waiting = False
        self._closed = False
        self.logger_type: str | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def set_device(self, device: BLEDevice) -> None:
        """Use a fresher BLEDevice (for example one routed through another proxy)."""
        self._device = device

    async def async_connect(self) -> None:
        async with self._connect_lock:
            if self._closed:
                raise TransportError("transport closed")
            if not self.connected:
                await self._async_open()

    async def _async_open(self) -> None:
        try:
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self._device.name or self._device.address,
                disconnected_callback=self._on_disconnect,
                ble_device_callback=lambda: self._device,
                max_attempts=3,
            )
            if self._closed:
                raise TransportError("transport closed while connecting")
            async with asyncio.timeout(SUBSCRIBE_TIMEOUT):
                await self._client.start_notify(NOTIFY_CHAR, self._on_notify)
            reply = await self._command(protocol.HANDSHAKE, protocol.handshake_complete)
            self.logger_type = protocol.parse_handshake(reply)
        except TransportError:
            await self.async_disconnect()
            raise
        except BaseException as err:
            # Includes cancellation: never leave a half-open session holding the
            # logger's only connection slot.
            await self.async_disconnect()
            if isinstance(err, Exception):
                raise TransportError(f"could not open a session: {err}") from err
            raise

    async def async_read(self, start: int, count: int) -> list[int]:
        if not self.connected:
            raise TransportError("not connected")
        reply = await self._command(
            protocol.read_command(start, count),
            lambda buffer: protocol.read_complete(buffer, count),
        )
        try:
            return protocol.parse_read(reply, count)
        except protocol.ExceptionReply as err:
            if err.code == protocol.ILLEGAL_DATA_ADDRESS:
                raise RegisterUnavailable(f"read {start:#06x}+{count}: {err}") from err
            raise TransportError(f"read {start:#06x}+{count}: {err}") from err
        except protocol.ProtocolError as err:
            raise TransportError(f"read {start:#06x}+{count}: {err}") from err

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            async with asyncio.timeout(10):
                await client.disconnect()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Disconnect from %s failed: %s", self._device.address, err)

    async def async_close(self) -> None:
        """Disconnect for good; later connection attempts are refused."""
        self._closed = True
        await self.async_disconnect()

    async def _command(self, text: str, complete: Callable[[str], bool]) -> str:
        async with self._lock:
            client = self._client
            if client is None:
                raise TransportError("not connected")
            self._buffer = ""
            self._received.clear()
            self._waiting = True
            try:
                async with asyncio.timeout(REPLY_TIMEOUT):
                    await client.write_gatt_char(
                        COMMAND_CHAR, (text + "\n").encode(), response=True
                    )
                    while not complete(self._buffer):
                        await self._received.wait()
                        self._received.clear()
                        if not client.is_connected:
                            raise TransportError("logger disconnected")
            except TransportError:
                raise
            except TimeoutError as err:
                raise TransportError(
                    f"no complete reply to {text.split(',')[0]} (got {self._buffer!r})"
                ) from err
            except Exception as err:  # noqa: BLE001
                raise TransportError(f"{type(err).__name__}: {err}") from err
            finally:
                self._waiting = False
            return self._buffer

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        if not self._waiting:
            return
        self._buffer += data.decode("ascii", errors="replace")
        self._received.set()

    def _on_disconnect(self, _client: object) -> None:
        _LOGGER.debug("Logger %s disconnected", self._device.address)
        self._received.set()
