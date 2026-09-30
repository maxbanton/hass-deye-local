"""BLE session tests against a scripted fake of the logger's GATT interface."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from custom_components.deye_local import protocol
from custom_components.deye_local.const import COMMAND_CHAR, NOTIFY_CHAR
from custom_components.deye_local.transport import (
    DeyeTransport,
    RegisterUnavailable,
    TransportError,
)

from .common import service_info

HANDSHAKE = "+ok=21511,21511"


def reply_for(start: int, count: int, values: list[int]) -> str:
    body = bytes([1, 3, 2 * count]) + b"".join(v.to_bytes(2, "big") for v in values)
    crc = protocol.crc16(body)
    return "+ok=" + (body + bytes([crc & 0xFF, crc >> 8])).hex().upper()


class FakeLogger:
    """Answers commands like the logger: replies arrive as one or more notifications."""

    def __init__(self, chunk: int = 20) -> None:
        self.chunk = chunk
        self.is_connected = True
        self.written: list[tuple[str, bytes, bool]] = []
        self.registers: dict[int, int] = {0: 3, 1: 0x0101}
        self.silent = False
        self.unavailable_from: int | None = None
        self._notify = None

    async def start_notify(self, char, callback) -> None:
        assert char == NOTIFY_CHAR
        self._notify = callback

    async def write_gatt_char(self, char, data: bytes, response: bool) -> None:
        self.written.append((char, data, response))
        if self.silent:
            return
        text = data.decode().strip()
        if text == protocol.HANDSHAKE:
            reply = HANDSHAKE
        else:
            frame = bytes.fromhex(text.split(",", 1)[1])
            start, count = frame[2] << 8 | frame[3], frame[5]
            if frame[1] == protocol.WRITE_MULTIPLE:
                data = frame[7:-2]
                for i in range(count):
                    self.registers[start + i] = data[2 * i] << 8 | data[2 * i + 1]
                body = frame[:6]
                crc = protocol.crc16(body)
                reply = "+ok=" + (body + bytes([crc & 0xFF, crc >> 8])).hex().upper()
            elif self.unavailable_from is not None and start >= self.unavailable_from:
                body = bytes([1, 0x83, 2])
                crc = protocol.crc16(body)
                reply = "+ok=" + (body + bytes([crc & 0xFF, crc >> 8])).hex().upper()
            else:
                values = [self.registers.get(start + i, 0) for i in range(count)]
                reply = reply_for(start, count, values)
        loop = asyncio.get_running_loop()
        for i in range(0, len(reply), self.chunk):
            loop.call_soon(self._notify, None, bytearray(reply[i : i + self.chunk].encode()))

    async def disconnect(self) -> None:
        self.is_connected = False


@pytest.fixture
def logger():
    fake = FakeLogger()

    async def connect(*args, **kwargs):
        fake.is_connected = True
        return fake

    with patch("custom_components.deye_local.transport.establish_connection", connect):
        yield fake


@pytest.fixture
def transport():
    return DeyeTransport(service_info().device)


async def test_handshake_without_line_ending(logger, transport) -> None:
    await transport.async_connect()
    assert transport.logger_type == "21511,21511"
    char, data, response = logger.written[0]
    assert (char, data, response) == (COMMAND_CHAR, b"AT+DTYPE\n", True)


async def test_reply_split_over_notifications_is_reassembled(logger, transport) -> None:
    logger.chunk = 7
    logger.registers.update({0x00B8: 86, 0x00B9: 0xFFD4})
    await transport.async_connect()
    assert await transport.async_read(0x00B8, 2) == [86, 0xFFD4]


async def test_only_handshake_and_register_reads_are_sent(logger, transport) -> None:
    await transport.async_connect()
    await transport.async_read(0x0000, 8)
    commands = [data.decode() for _, data, _ in logger.written]
    assert commands[0] == "AT+DTYPE\n"
    assert all(c.startswith("AT+INVDATA=8,0103") for c in commands[1:])


async def test_exception_reply_means_register_unavailable(logger, transport) -> None:
    logger.unavailable_from = 0x2700
    await transport.async_connect()
    with pytest.raises(RegisterUnavailable):
        await transport.async_read(0x2730, 8)
    assert await transport.async_read(0x0000, 1) == [3]


async def test_silence_times_out_and_the_next_command_recovers(logger, transport) -> None:
    await transport.async_connect()
    logger.silent = True
    with (
        patch("custom_components.deye_local.transport.REPLY_TIMEOUT", 0.05),
        pytest.raises(TransportError, match="no complete reply"),
    ):
        await transport.async_read(0x0000, 1)
    logger.silent = False
    assert await transport.async_read(0x0000, 1) == [3]


async def test_concurrent_reads_are_serialised(logger, transport) -> None:
    logger.registers.update({0x0010: 111, 0x0020: 222})
    await transport.async_connect()
    first, second = await asyncio.gather(
        transport.async_read(0x0010, 1), transport.async_read(0x0020, 1)
    )
    assert (first, second) == ([111], [222])


async def test_failed_handshake_closes_the_session(logger, transport) -> None:
    logger.silent = True
    with (
        patch("custom_components.deye_local.transport.REPLY_TIMEOUT", 0.05),
        pytest.raises(TransportError),
    ):
        await transport.async_connect()
    assert not transport.connected
    assert not logger.is_connected


async def test_reading_without_a_session_fails_cleanly(transport) -> None:
    with pytest.raises(TransportError, match="not connected"):
        await transport.async_read(0x0000, 1)


async def test_disconnect_during_a_command_fails_fast(logger, transport) -> None:
    await transport.async_connect()
    logger.silent = True
    task = asyncio.create_task(transport.async_read(0x0000, 1))
    await asyncio.sleep(0)
    logger.is_connected = False
    transport._on_disconnect(None)
    with pytest.raises(TransportError, match="disconnected"):
        await asyncio.wait_for(task, 1)


async def test_late_reply_is_not_taken_for_the_next_one(logger, transport) -> None:
    await transport.async_connect()
    logger.registers[0x0010] = 111
    transport._on_notify(None, bytearray(reply_for(0x0099, 1, [999]).encode()))
    assert await transport.async_read(0x0010, 1) == [111]


async def test_closed_transport_refuses_to_reconnect(logger, transport) -> None:
    await transport.async_connect()
    await transport.async_close()
    assert not logger.is_connected
    with pytest.raises(TransportError, match="closed"):
        await transport.async_connect()


async def test_close_while_connecting_releases_the_logger(transport) -> None:
    fake = FakeLogger()
    started = asyncio.Event()

    async def slow_connect(*args, **kwargs):
        started.set()
        await asyncio.sleep(0.05)
        return fake

    with patch("custom_components.deye_local.transport.establish_connection", slow_connect):
        connecting = asyncio.create_task(transport.async_connect())
        await started.wait()
        await transport.async_close()
        with pytest.raises(TransportError):
            await connecting
    assert not fake.is_connected
    assert not transport.connected


async def test_cancelled_open_releases_the_logger(transport) -> None:
    fake = FakeLogger()
    fake.silent = True

    async def connect(*args, **kwargs):
        return fake

    with patch("custom_components.deye_local.transport.establish_connection", connect):
        task = asyncio.create_task(transport.async_connect())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not fake.is_connected


async def test_hung_write_times_out(logger, transport) -> None:
    await transport.async_connect()

    async def hang(*args, **kwargs):
        await asyncio.sleep(10)

    logger.write_gatt_char = hang
    with (
        patch("custom_components.deye_local.transport.REPLY_TIMEOUT", 0.05),
        pytest.raises(TransportError, match="no complete reply"),
    ):
        await transport.async_read(0x0000, 1)


@pytest.mark.parametrize(
    "code,error",
    [(2, RegisterUnavailable), (6, TransportError)],
    ids=["illegal-address", "slave-busy"],
)
async def test_only_illegal_address_means_unavailable(logger, transport, code, error) -> None:
    await transport.async_connect()
    body = bytes([1, 0x83, code])
    crc = protocol.crc16(body)
    reply = "+ok=" + (body + bytes([crc & 0xFF, crc >> 8])).hex().upper()

    async def answer(char, data, response):
        asyncio.get_running_loop().call_soon(logger._notify, None, bytearray(reply.encode()))

    logger.write_gatt_char = answer
    with pytest.raises(error) as caught:
        await transport.async_read(0x2730, 8)
    if error is TransportError:
        assert not isinstance(caught.value, RegisterUnavailable)


async def test_write_sends_write_multiple_and_checks_the_echo(logger, transport) -> None:
    await transport.async_connect()
    await transport.async_write(0x00D2, [50])
    assert logger.registers[0x00D2] == 50
    command = logger.written[-1][1].decode()
    assert command.startswith("AT+INVDATA=11,011000D2000102")
    assert await transport.async_read(0x00D2, 1) == [50]
