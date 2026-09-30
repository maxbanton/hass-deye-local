"""Tests for the logger's command framing."""
from __future__ import annotations

import pytest

from custom_components.deye_local import protocol
from custom_components.deye_local.protocol import ProtocolError

from .snapshot import SERIAL_WORDS


def test_read_frame_matches_a_known_request():
    # Read one register at 0x0002, as captured from the vendor app.
    assert protocol.read_frame(0x0002, 1).hex().upper() == "01030002000125CA"


def test_read_command_wraps_the_frame():
    assert protocol.read_command(0x0002, 1) == "AT+INVDATA=8,01030002000125CA"


@pytest.mark.parametrize("start,count", [(-1, 1), (0x10000, 1), (0, 0), (0, 126)])
def test_read_frame_rejects_invalid_ranges(start, count):
    with pytest.raises(ValueError):
        protocol.read_frame(start, count)


def test_parse_read_returns_register_values():
    assert protocol.parse_read("+ok=0103020104B817", 1) == [0x0104]


def test_parse_read_ignores_trailing_line_ending():
    assert protocol.parse_read("+ok=0103020104B817\r\n", 1) == [0x0104]


def test_parse_read_rejects_a_bad_crc():
    with pytest.raises(ProtocolError, match="CRC"):
        protocol.parse_read("+ok=0103020104B818", 1)


def test_parse_read_reports_modbus_exceptions():
    frame = bytes([0x01, 0x83, 0x02])
    crc = protocol.crc16(frame)
    reply = "+ok=" + (frame + bytes([crc & 0xFF, crc >> 8])).hex().upper()
    assert protocol.read_complete(reply, 4)
    with pytest.raises(ProtocolError, match="rejected"):
        protocol.parse_read(reply, 4)


def test_parse_read_rejects_an_error_reply():
    with pytest.raises(ProtocolError):
        protocol.parse_read("+ERR=-1", 1)


def test_read_complete_waits_for_the_whole_frame():
    assert not protocol.read_complete("+ok=01030201", 1)
    assert protocol.read_complete("+ok=0103020104B817", 1)
    assert protocol.read_complete("+ERR=-1\n", 1)


def test_handshake_without_line_ending_is_complete():
    assert protocol.handshake_complete("+ok=21511,21511")
    assert not protocol.handshake_complete("+ok=2151")
    assert protocol.parse_handshake("+ok=21511,21511") == "21511,21511"


def test_parse_handshake_rejects_garbage():
    with pytest.raises(ProtocolError):
        protocol.parse_handshake("hello")


def test_plan_blocks_merges_small_gaps_and_caps_length():
    assert protocol.plan_blocks({1, 2, 3, 6, 20}, 16) == [(1, 6), (20, 1)]
    assert protocol.plan_blocks(range(40), 16) == [(0, 16), (16, 16), (32, 8)]


def test_decode_ascii_serial():
    assert protocol.decode_ascii(SERIAL_WORDS) == "2603125693"


def test_write_frame_matches_a_known_request():
    frame = protocol.write_frame(0x00D2, [40])
    assert frame[:9] == bytes.fromhex("011000D200010200 28".replace(" ", ""))
    assert protocol.crc16(frame[:-2]) == frame[-2] | frame[-1] << 8


def test_write_command_wraps_the_frame():
    assert protocol.write_command(0x00D2, [40]).startswith("AT+INVDATA=11,011000D2")


@pytest.mark.parametrize(("start", "values"), [(0, []), (0, [0x10000]), (0, [-1])])
def test_write_frame_rejects_invalid_values(start, values):
    with pytest.raises(ValueError):
        protocol.write_frame(start, values)


def _write_reply(body: bytes) -> str:
    crc = protocol.crc16(body)
    return "+ok=" + (body + bytes([crc & 0xFF, crc >> 8])).hex().upper()


def test_parse_write_accepts_the_echo():
    reply = _write_reply(bytes.fromhex("011000D20001"))
    assert protocol.write_complete(reply)
    protocol.parse_write(reply, 0x00D2, 1)


def test_parse_write_rejects_a_different_address():
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_write(_write_reply(bytes.fromhex("011000D30001")), 0x00D2, 1)


def test_parse_write_reports_modbus_exceptions():
    reply = _write_reply(bytes.fromhex("019003"))
    assert protocol.write_complete(reply)
    with pytest.raises(protocol.ExceptionReply):
        protocol.parse_write(reply, 0x00D2, 1)


def test_write_complete_waits_for_the_whole_frame():
    assert not protocol.write_complete("+ok=011000D2")
