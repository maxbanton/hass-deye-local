"""Config and options flow tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deye_local.config_flow import Identity
from custom_components.deye_local.const import (
    CONF_DEVICE_TYPE,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DOMAIN,
)
from custom_components.deye_local.transport import TransportError

from .common import ADDRESS, NAME, service_info

IDENTIFY = "custom_components.deye_local.config_flow.async_identify"
DISCOVERED = (
    "custom_components.deye_local.config_flow.bluetooth.async_discovered_service_info"
)
SINGLE_PHASE = Identity(device_type=0x0003, serial="2603125693")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.deye_local.async_setup_entry", return_value=True):
        yield


async def _discover(hass: HomeAssistant, info=None, identify=None):
    """Run discovery up to the step after the user agrees to connect."""
    identify = identify or AsyncMock(return_value=SINGLE_PHASE)
    with patch(IDENTIFY, identify):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info or service_info()
        )
        assert result["step_id"] == "bluetooth_confirm"
        identify.assert_not_awaited()
        return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_discovery_does_not_connect_before_confirmation(hass: HomeAssistant) -> None:
    identify = AsyncMock(return_value=SINGLE_PHASE)
    with patch(IDENTIFY, identify):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
        )
    assert result["step_id"] == "bluetooth_confirm"
    identify.assert_not_awaited()


async def test_bluetooth_discovery_creates_an_entry(hass: HomeAssistant) -> None:
    result = await _discover(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    placeholders = result["description_placeholders"]
    assert placeholders["model"] == "Single phase hybrid"
    assert placeholders["serial"] == "2603125693"
    assert placeholders["support"] == "Supported."

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Deye Single phase hybrid"
    assert result["data"] == {
        CONF_ADDRESS: ADDRESS,
        CONF_DEVICE_TYPE: 3,
        CONF_SERIAL: "2603125693",
    }
    assert result["result"].unique_id == ADDRESS


async def test_experimental_family_is_flagged(hass: HomeAssistant) -> None:
    result = await _discover(hass, identify=AsyncMock(return_value=Identity(0x0005, "X")))
    assert result["description_placeholders"]["support"].startswith("Experimental")


async def test_unreachable_logger_offers_a_retry(hass: HomeAssistant) -> None:
    result = await _discover(hass, identify=AsyncMock(side_effect=TransportError("timeout")))
    assert result["step_id"] == "identify"
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(IDENTIFY, AsyncMock(return_value=SINGLE_PHASE)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "confirm"


async def test_discovery_of_a_configured_logger_aborts(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_without_loggers_explains_what_is_needed(
    hass: HomeAssistant,
) -> None:
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_picks_a_discovered_logger(hass: HomeAssistant) -> None:
    with patch(DISCOVERED, return_value=[service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["step_id"] == "user"
    with patch(IDENTIFY, AsyncMock(return_value=SINGLE_PHASE)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["logger"] == NAME


async def test_options_flow_enforces_the_minimum_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    with pytest.raises(Exception):  # noqa: B017
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 5}
        )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_KEEP_CONNECTED: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 30, CONF_KEEP_CONNECTED: False}


async def test_logger_without_a_name_gets_a_readable_label(hass: HomeAssistant) -> None:
    # Passive scanners never see the scan response that carries the logger's name.
    result = await _discover(hass, info=service_info(name=ADDRESS))
    assert result["description_placeholders"]["logger"] == f"Deye data logger {ADDRESS}"
