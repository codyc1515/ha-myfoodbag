"""Startup must not wait for account requests, including on entry reload."""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant

from mfb.api import ApiError, AuthError
from mfb.calendar import async_setup_entry as setup_calendars


@pytest_asyncio.fixture
async def account(tmp_path):
    module = importlib.import_module('mfb.__init__')
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    entry = ConfigEntry(
        version=1, minor_version=1, domain='myfoodbag', title='My Food Bag',
        data={'email': 'test@example.invalid', 'password': 'dummy'},
        options={}, source='user', unique_id=None, discovery_keys={},
        subentries_data=None,
    )
    client = Mock(get=AsyncMock())
    calendars = Mock()

    async def forward(entry, platforms):
        await setup_calendars(hass, entry, calendars)

    with patch.object(module, 'async_get_clientsession'), \
         patch.object(module, 'Client', return_value=client), \
         patch.object(module.er, 'async_get'), \
         patch.object(module.er, 'async_entries_for_config_entry', return_value=[]), \
         patch.object(hass.config_entries, 'async_forward_entry_setups', side_effect=forward):
        try:
            yield module, hass, entry, client, calendars
        finally:
            await entry._async_process_on_unload(hass)
            await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('already_running', [False, True])
async def test_initial_refresh_is_background_and_discovers_calendars(account, already_running):
    module, hass, entry, client, calendars = account
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_request(path):
        started.set()
        await release.wait()
        return [{'product': {'productName': 'Fresh Start for 4 people'}, 'orders': []}]

    client.get.side_effect = slow_request
    if already_running:
        hass.set_state(CoreState.running)

    assert await asyncio.wait_for(module.async_setup_entry(hass, entry), timeout=1)
    assert entry.runtime_data.data == {}
    if not already_running:
        client.get.assert_not_called()
        hass.set_state(CoreState.running)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)

    await asyncio.wait_for(started.wait(), timeout=1)
    # Startup's task drain must complete even while the account request is pending.
    await asyncio.wait_for(hass.async_block_till_done(), timeout=1)
    assert entry.runtime_data.data == {}

    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.get.assert_awaited_once_with('/subscriptions/orders')
    assert set(entry.runtime_data.data) == {'Fresh Start'}
    entities = calendars.call_args.args[0]
    assert len(entities) == 1
    assert entities[0].bag == 'Fresh Start'


@pytest.mark.asyncio
async def test_unload_before_start_cancels_deferred_refresh(account):
    module, hass, entry, client, _ = account
    assert await module.async_setup_entry(hass, entry)
    await entry._async_process_on_unload(hass)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_unload_cancels_pending_account_request(account):
    module, hass, entry, client, _ = account
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_request(path):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client.get.side_effect = slow_request
    hass.set_state(CoreState.running)
    assert await module.async_setup_entry(hass, entry)
    await asyncio.wait_for(started.wait(), timeout=1)
    await entry._async_process_on_unload(hass)
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_failed_initial_refresh_recovers_on_later_poll(account):
    module, hass, entry, client, calendars = account
    client.get.side_effect = [ApiError('Unavailable'), [
        {'product': {'productName': 'Fresh Start for 4 people'}, 'orders': []}
    ]]
    hass.set_state(CoreState.running)
    assert await module.async_setup_entry(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator = entry.runtime_data
    assert not coordinator.last_update_success
    assert coordinator.data == {}
    assert coordinator._unsub_refresh is not None

    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert calendars.call_args.args[0][0].bag == 'Fresh Start'


@pytest.mark.asyncio
async def test_background_auth_failure_starts_reauth(account):
    module, hass, entry, client, _ = account
    client.get.side_effect = AuthError('Expired credentials')
    hass.set_state(CoreState.running)
    with patch.object(ConfigEntry, 'async_start_reauth_if_available') as reauth:
        assert await module.async_setup_entry(hass, entry)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert not entry.runtime_data.last_update_success
    reauth.assert_called_once_with(hass)
