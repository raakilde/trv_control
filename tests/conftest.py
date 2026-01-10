"""Fixtures for TRV Control tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.components.climate import HVACMode
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.trv_control.const import DOMAIN
from .const import MOCK_CONFIG_ENTRY_DATA, MOCK_TEMP_SENSOR, MOCK_TRV_1, MOCK_TRV_2


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_ENTRY_DATA,
        entry_id="test_entry",
        title="TRV Control",
    )


@pytest.fixture
def mock_hass():
    """Return a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.fixture
def mock_state():
    """Return a mock state object."""
    def _mock_state(entity_id, state, attributes=None):
        mock = MagicMock()
        mock.entity_id = entity_id
        mock.state = state
        mock.attributes = attributes or {}
        return mock
    return _mock_state
