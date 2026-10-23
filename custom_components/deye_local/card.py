"""Serve the time of use card and load it on the dashboards."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

FRONTEND_URL = f"/{DOMAIN}/frontend"
FRONTEND_PATH = Path(__file__).parent / "frontend"
CARD_URL = f"{FRONTEND_URL}/deye-local-tou-card.js"


def _resources(hass: HomeAssistant) -> ResourceStorageCollection | None:
    """The dashboard resources, when they are managed in the UI."""
    resources = getattr(hass.data.get("lovelace"), "resources", None)
    return resources if isinstance(resources, ResourceStorageCollection) else None


def _is_card(item: dict) -> bool:
    return item["url"].split("?")[0] == CARD_URL


async def async_serve_card(hass: HomeAssistant) -> None:
    """Serve the card and load it as a dashboard resource.

    A resource rather than an extra module: the frontend's service worker caches
    the page that lists extra modules, so a page cached while Home Assistant was
    starting stays without the card. Resources are fetched on every load.

    The frontend is only an after-dependency, so setups without it (tests,
    headless installs) still load the integration.
    """
    if "frontend" not in hass.config.components or hass.http is None:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(FRONTEND_PATH), True)]
    )
    if _resources(hass) is None:
        add_extra_js_url(hass, await _versioned_url(hass))
    else:
        await async_add_card_resource(hass)


async def _versioned_url(hass: HomeAssistant) -> str:
    """The card URL with the version that busts browser caches on updates."""
    return f"{CARD_URL}?v={(await async_get_integration(hass, DOMAIN)).version}"


async def async_add_card_resource(hass: HomeAssistant) -> None:
    """Add the card to the dashboard resources, or move it to this version."""
    if (resources := _resources(hass)) is None:
        return
    await resources.async_get_info()
    url = await _versioned_url(hass)
    current, *duplicates = [item for item in resources.async_items() if _is_card(item)] or [None]
    for item in duplicates:
        await resources.async_delete_item(item["id"])
    if current is None:
        await resources.async_create_item({"res_type": "module", "url": url})
    elif current["url"] != url:
        await resources.async_update_item(current["id"], {"res_type": "module", "url": url})


async def async_remove_card_resource(hass: HomeAssistant) -> None:
    if (resources := _resources(hass)) is None:
        return
    await resources.async_get_info()
    for item in resources.async_items():
        if _is_card(item):
            await resources.async_delete_item(item["id"])
