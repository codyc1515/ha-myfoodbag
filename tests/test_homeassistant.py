"""Exercise actual Home Assistant entity classes with synthetic account data."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
import pytest
from homeassistant.core import HomeAssistant
from mfb.calendar import BagCalendar
from mfb.sensor import DeliverySensor, SENSORS
from mfb.binary_sensor import DeliveryBinary
from mfb.coordinator import Coordinator
from mfb.config_flow import ConfigFlow
from mfb.models import normalize, NZ


def setup_data():
    day=datetime.now(NZ).date().isoformat()
    d=normalize({'product':{'productName':'Fresh Start for 4 people'}},
                {'orderKey':'synthetic','deliveryDate':{'actualDeliveryDate':day,'actualDeliveryStartTime':'07:00:00','actualDeliveryEndTime':'17:00:00'},'totalCost':123.49},
                {'primaryProductName':'Fresh Start Choice (5 Nights For 4)','total':123.49,'paid':True,'extras':[{'productName':'Shop Flowers Flyer','price':0}]},
                tracking={'trackingNumber':'TEST123'})
    return SimpleNamespace(data={'Fresh Start':[d]},last_update_success=True),SimpleNamespace(entry_id='test'),d

@pytest.mark.asyncio
async def test_calendar_overlap():
    c,e,d=setup_data();entity=BagCalendar(c,e,'Fresh Start','calendar',None)
    assert (await entity.async_get_events(None,d.start,d.end))[0].summary=='5 meals for 4 people'
    assert await entity.async_get_events(None,d.end,d.end+timedelta(hours=1))==[]
    assert await entity.async_get_events(None,d.start-timedelta(hours=1),d.start)==[]
    assert entity.device_info['name']=='Fresh Start'

def test_sensor_values():
    c,e,d=setup_data()
    sensors={s[0]:DeliverySensor(c,e,'Fresh Start',*s) for s in SENSORS}
    assert str(sensors['price'].native_value)=='123.49'
    assert sensors['price'].native_unit_of_measurement=='NZD'
    assert sensors['tracking_number'].native_value=='TEST123'
    assert sensors['window_start'].native_value.hour==7
    assert sensors['window_start'].extra_state_attributes['window_end']==d.end.isoformat()

def test_binary_values_clear_when_no_delivery():
    c,e,d=setup_data();b=DeliveryBinary(c,e,'Fresh Start','promo_items','Promotional items')
    assert b.is_on is True
    c.data={}
    assert b.is_on is None

@pytest.mark.asyncio
async def test_config_flow_form(tmp_path):
    flow=ConfigFlow();flow.hass=HomeAssistant(str(tmp_path))
    result=await flow.async_step_user()
    assert result['type']=='form'
    assert set(str(k) for k in result['data_schema'].schema)=={'email','password'}

@pytest.mark.asyncio
async def test_config_flow_bad_auth(tmp_path):
    from mfb.api import AuthError
    flow=ConfigFlow();flow.hass=HomeAssistant(str(tmp_path))
    with patch('mfb.config_flow.async_get_clientsession'),patch('mfb.config_flow.Client.get',new=AsyncMock(side_effect=AuthError)):
        result=await flow.async_step_user({'email':'test@example.invalid','password':'dummy'})
    assert result['errors']=={'base':'invalid_auth'}

@pytest.mark.asyncio
async def test_coordinator_combines_subscriptions(tmp_path):
    hass=HomeAssistant(str(tmp_path))
    order={'orderKey':'a','isVirtual':True,'deliveryDate':{'actualDeliveryDate':'2026-09-12'},'primaryProduct':{'marketingName':'Fresh Start for 4 people'}}
    subscriptions=[{'product':{'productName':'Fresh Start for 4 people'},'orders':[order]},
                   {'product':{'productName':'Fresh Start for 4 people'},'orders':[{**order,'orderKey':'b'}]}]
    client=SimpleNamespace(get=AsyncMock(return_value=subscriptions))
    c=Coordinator(hass,None,client)
    result=await c._async_update_data()
    assert list(result)==['Fresh Start']
    assert len(result['Fresh Start'])==2


@pytest.mark.asyncio
async def test_reauth_form_requires_only_credentials(tmp_path):
    flow = ConfigFlow()
    flow.hass = HomeAssistant(str(tmp_path))
    result = await flow.async_step_reauth({})
    assert set(str(k) for k in result['data_schema'].schema) == {'email', 'password'}


@pytest.mark.asyncio
async def test_setup_with_credentials():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        'mfb.setup', Path(__file__).parents[1] / 'custom_components/myfoodbag/__init__.py',
        submodule_search_locations=None
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = {'email': 'test@example.invalid', 'password': 'dummy'}
    entry = SimpleNamespace(data=data)
    manager = SimpleNamespace(async_forward_entry_setups=AsyncMock())
    hass = SimpleNamespace(config_entries=manager)
    coordinator = SimpleNamespace(async_config_entry_first_refresh=AsyncMock())
    with patch.object(module, 'async_get_clientsession', return_value='session'), \
         patch.object(module, 'Client') as client, \
         patch.object(module, 'Coordinator', return_value=coordinator):
        assert await module.async_setup_entry(hass, entry)
    client.assert_called_once_with('session', data['email'], data['password'])
    assert entry.data == data


@pytest.mark.asyncio
@pytest.mark.parametrize('delivery_day', ['2026-09-12', '2026-09-26'])
async def test_all_day_meals_across_five_days(delivery_day):
    from datetime import date
    from homeassistant.util import dt as dt_util

    d = normalize(
        {'product': {'productName': 'Fresh Start for 4 people'}},
        {'orderKey': 'meals', 'deliveryDate': {
            'actualDeliveryDate': delivery_day,
            'actualDeliveryStartTime': '07:00:00',
            'actualDeliveryEndTime': '17:00:00'}},
        {'primaryProductName': 'Fresh Start Choice (5 Nights For 4)'},
        {'recipes': [{'recipeName': f'Meal {i}', 'timeStamp': i}
                     for i in [5, 2, 1, 4, 3]]},
    )
    c = SimpleNamespace(data={'Fresh Start': [d]}, last_update_success=True)
    entity = BagCalendar(c, SimpleNamespace(entry_id='test'), 'Fresh Start', 'calendar', None)
    with patch.object(dt_util, 'DEFAULT_TIME_ZONE', NZ):
        events = await entity.async_get_events(None, d.start - timedelta(days=1), d.end + timedelta(days=6))
        meals = [event for event in events if event.all_day]
        assert len(events) == 6
        assert [event.summary for event in meals] == [f'Meal {i}' for i in range(1, 6)]
        first = date.fromisoformat(delivery_day)
        assert [event.start for event in meals] == [first + timedelta(days=i) for i in range(5)]
        assert all(type(event.start) is date and event.end == event.start + timedelta(days=1)
                   for event in meals)
        # Queries after delivery still return meals, including across the DST change.
        midday = d.start.replace(hour=12) + timedelta(days=2)
        assert [e.summary for e in await entity.async_get_events(None, midday, midday + timedelta(hours=1))] == ['Meal 3']
        with patch('mfb.calendar.dt_util.now', return_value=midday):
            assert entity.event.summary == 'Meal 3'
        final_end = meals[-1].end_datetime_local
        assert await entity.async_get_events(None, final_end, final_end + timedelta(days=1)) == []
        assert await entity.async_get_events(None, meals[0].start_datetime_local - timedelta(days=1), meals[0].start_datetime_local) == []
        with patch('mfb.calendar.dt_util.now', return_value=final_end):
            assert entity.event is None
