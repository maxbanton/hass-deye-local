"""The time of use card: served by the integration and loaded on the dashboards."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deye_local.card import CARD_URL, FRONTEND_PATH
from custom_components.deye_local.const import DOMAIN

from .test_init import (  # noqa: F401
    _setup,
    auto_enable_custom_integrations,
    bluetooth_device,
    fake_transport,
)


@pytest.fixture(autouse=True)
def frontend(hass: HomeAssistant) -> None:
    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())


@pytest.fixture
def resources(hass: HomeAssistant) -> ResourceStorageCollection:
    collection = ResourceStorageCollection(hass, MagicMock(async_load=AsyncMock(return_value={})))
    hass.data["lovelace"] = SimpleNamespace(resources=collection)
    return collection


async def _version(hass: HomeAssistant) -> str:
    from homeassistant.loader import async_get_integration

    return (await async_get_integration(hass, DOMAIN)).version


def _urls(resources: ResourceStorageCollection) -> list[str]:
    return [item["url"] for item in resources.async_items()]


async def test_card_files_are_served(hass: HomeAssistant, resources) -> None:
    await _setup(hass)
    (paths,), _ = hass.http.async_register_static_paths.call_args
    assert paths[0].url_path == "/deye_local/frontend"
    assert (FRONTEND_PATH / "deye-local-tou-card.js").is_file()
    assert (FRONTEND_PATH / "tou-card-core.js").is_file()


async def test_card_is_added_to_the_dashboard_resources(hass: HomeAssistant, resources) -> None:
    with patch("custom_components.deye_local.card.add_extra_js_url") as add_url:
        await _setup(hass)
    add_url.assert_not_called()
    assert _urls(resources) == [f"{CARD_URL}?v={await _version(hass)}"]
    assert resources.async_items()[0]["type"] == "module"


async def test_update_moves_the_resource_to_the_new_version(
    hass: HomeAssistant, resources
) -> None:
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=0.1.0"})
    await resources.async_create_item({"res_type": "js", "url": CARD_URL})
    await _setup(hass)
    assert _urls(resources) == ["/local/other-card.js", f"{CARD_URL}?v={await _version(hass)}"]


async def test_yaml_dashboards_load_the_card_with_the_page(hass: HomeAssistant) -> None:
    hass.data["lovelace"] = SimpleNamespace(resources=ResourceYAMLCollection([]))
    with patch("custom_components.deye_local.card.add_extra_js_url") as add_url:
        await _setup(hass)
    add_url.assert_called_once_with(hass, f"{CARD_URL}?v={await _version(hass)}")


async def test_removing_the_last_entry_removes_the_resource(
    hass: HomeAssistant, resources
) -> None:
    entry = await _setup(hass)
    other = MockConfigEntry(domain=DOMAIN, unique_id="AA:BB:CC:DD:EE:FF", data={})
    other.add_to_hass(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    assert len(_urls(resources)) == 1
    await hass.config_entries.async_remove(other.entry_id)
    assert _urls(resources) == []


async def test_a_new_entry_restores_a_removed_resource(hass: HomeAssistant, resources) -> None:
    entry = await _setup(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    assert _urls(resources) == []
    await _setup(hass)
    assert _urls(resources) == [f"{CARD_URL}?v={await _version(hass)}"]

