"""Diagnostics tests."""
from __future__ import annotations

import pytest

from .test_init import _setup, bluetooth_device, fake_transport  # noqa: F401

diagnostics_helper = pytest.importorskip(
    "pytest_homeassistant_custom_component.components.diagnostics",
    reason="diagnostics test helper not available in this test framework release",
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


async def test_diagnostics_include_a_register_dump(hass, hass_client) -> None:
    entry = await _setup(hass)
    diagnostics = await diagnostics_helper.get_diagnostics_for_config_entry(
        hass, hass_client, entry
    )
    assert diagnostics["family"] == {
        "key": "single_phase_hybrid",
        "name": "Single phase hybrid",
        "support": "supported",
    }
    assert diagnostics["polled_registers"]["00B8"] == 86
    assert diagnostics["register_dump"]["0000"][0] == 3
    assert diagnostics["logger"]["handshake"] == "21511,21511"
    assert diagnostics["logger"]["source"] == "local"


async def test_diagnostics_redact_identifiers(hass, hass_client) -> None:
    entry = await _setup(hass)
    diagnostics = await diagnostics_helper.get_diagnostics_for_config_entry(
        hass, hass_client, entry
    )
    text = str(diagnostics)
    for secret in ("2603125693", "88:A6:8D:2C:4F:15", "D26109249480", "25007000E4020510"):
        assert secret not in text
    assert diagnostics["entry"]["data"]["serial"] == "**REDACTED**"
    assert diagnostics["register_dump"]["0000"][3:8] == ["**REDACTED**"] * 5
    assert diagnostics["register_dump"]["2730"][:8] == ["**REDACTED**"] * 8
    assert diagnostics["register_dump"]["2730"][8] == 537  # battery 1 voltage stays
    assert diagnostics["batteries"] == [
        {"slot": 1, "serial": "**REDACTED**"},
        {"slot": 2, "serial": "**REDACTED**"},
    ]
