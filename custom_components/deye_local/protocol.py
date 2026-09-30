"""Framing for the WiBLE logger's local command channel, independent of Home Assistant.

The logger speaks ASCII over BLE:

* ``AT+DTYPE`` is the handshake; the reply is ``+ok=<a>,<b>``.
* ``AT+INVDATA=<n>,<hex>`` forwards a Modbus RTU frame of ``n`` bytes to the
  inverter; the reply is ``+ok=<hex>`` carrying the inverter's Modbus response.

Replies can arrive split over several notifications and without a line ending,
so completeness is judged from the content rather than a terminator.
"""
from __future__ import annotations

import re

HANDSHAKE = "AT+DTYPE"
SLAVE_ID = 0x01
READ_HOLDING = 0x03
ILLEGAL_DATA_ADDRESS = 0x02

_OK = "+ok="
_HANDSHAKE_RE = re.compile(r"\+ok=\d+,\d+")


class ProtocolError(Exception):
    """A reply could not be parsed or failed validation."""


class ExceptionReply(ProtocolError):
    """The inverter answered with a Modbus exception."""

    def __init__(self, code: int) -> None:
        super().__init__(f"inverter rejected the read (exception {code})")
        self.code = code


def crc16(data: bytes) -> int:
    """CRC-16/Modbus."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def read_frame(start: int, count: int) -> bytes:
    """Modbus RTU 'read holding registers' request, CRC low byte first."""
    if not 0 <= start <= 0xFFFF or not 1 <= count <= 125:
        raise ValueError(f"invalid read {start:#06x}+{count}")
    body = bytes([SLAVE_ID, READ_HOLDING, start >> 8, start & 0xFF, 0, count])
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def read_command(start: int, count: int) -> str:
    frame = read_frame(start, count)
    return f"AT+INVDATA={len(frame)},{frame.hex().upper()}"


def is_error(buffer: str) -> bool:
    return "ERR" in buffer.upper()


def handshake_complete(buffer: str) -> bool:
    return _HANDSHAKE_RE.search(buffer) is not None or is_error(buffer)


def parse_handshake(buffer: str) -> str:
    match = _HANDSHAKE_RE.search(buffer)
    if match is None:
        raise ProtocolError(f"unexpected handshake reply {buffer.strip()!r}")
    return match.group(0)[len(_OK):]


def _expected_hex_length(count: int) -> int:
    # slave, function, byte count, data, crc (2)
    return (5 + 2 * count) * 2


def read_complete(buffer: str, count: int) -> bool:
    if _OK not in buffer:
        return is_error(buffer)
    payload = buffer.split(_OK, 1)[1].strip()
    # Modbus exception replies are shorter than a data reply.
    try:
        if len(payload) >= 10 and int(payload[2:4], 16) & 0x80:
            return True
    except ValueError:
        return True
    return len(payload) >= _expected_hex_length(count)


def parse_read(buffer: str, count: int) -> list[int]:
    if _OK not in buffer:
        raise ProtocolError(f"logger returned {buffer.strip()!r}")
    payload = buffer.split(_OK, 1)[1].strip()
    try:
        raw = bytes.fromhex(payload[: _expected_hex_length(count)])
    except ValueError as err:
        raise ProtocolError(f"reply is not hex: {payload!r}") from err
    if len(raw) >= 5 and raw[1] & 0x80:
        raise ExceptionReply(raw[2])
    if len(raw) != 5 + 2 * count:
        raise ProtocolError(f"short reply: {payload!r}")
    if crc16(raw[:-2]) != raw[-2] | raw[-1] << 8:
        raise ProtocolError("reply failed its CRC check")
    if raw[0] != SLAVE_ID or raw[1] != READ_HOLDING or raw[2] != 2 * count:
        raise ProtocolError(f"unexpected reply header: {raw[:3].hex()}")
    data = raw[3:-2]
    return [data[i] << 8 | data[i + 1] for i in range(0, len(data), 2)]


def plan_blocks(
    addresses: set[int] | list[int], max_block: int, max_gap: int = 4
) -> list[tuple[int, int]]:
    """Group register addresses into as few reads as possible.

    Neighbouring addresses are merged when the gap between them is small, and no
    read is longer than ``max_block`` registers.
    """
    blocks: list[tuple[int, int]] = []
    for address in sorted(set(addresses)):
        if blocks:
            start, count = blocks[-1]
            end = start + count - 1
            if address - end <= max_gap + 1 and address - start < max_block:
                blocks[-1] = (start, address - start + 1)
                continue
        blocks.append((address, 1))
    return blocks


def decode_ascii(words: list[int], swapped: bool = False) -> str:
    """Decode registers holding two ASCII characters each.

    Battery modules store the low byte first, the inverter the high byte first.
    """
    chars = []
    for word in words:
        pair = (word & 0xFF, word >> 8) if swapped else (word >> 8, word & 0xFF)
        chars.extend(pair)
    return bytes(c for c in chars if 32 <= c < 127).decode("ascii").strip()
