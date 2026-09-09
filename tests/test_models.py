from copy import deepcopy
from decimal import Decimal
import pytest
from mfb.models import normalize, current, timestamp, bag_name

@pytest.fixture
def data():
    return ({"product": {"productName": "Fresh Start for 4 people"}},
            {"orderKey": "sample", "deliveryDate": {"actualDeliveryDate": "2026-09-12T00:00:00",
              "actualDeliveryStartTime": "07:00:00", "actualDeliveryEndTime": "17:00:00"},
             "primaryProduct": {"marketingName": "Fresh Start for 4 people"}, "totalCost": 123.49,
             "isPaid": True, "isVirtual": False},
            {"primaryProductName": "Fresh Start Choice (5 Nights For 4)", "total": 123.49,
             "promoDiscount": 123.50, "extras": [{"productName": "Shop Flowers Flyer", "price": 0, "quantity": 1}],
             "products": [{"productName": "Shop Flowers Flyer", "price": 0, "quantity": 1}]})

def test_confirmed(data):
    d = normalize(*data)
    assert d.bag == "Fresh Start"
    assert d.title == "5 meals for 4 people"
    assert d.price == Decimal("123.49")
    assert d.start.isoformat() == "2026-09-12T07:00:00+12:00"
    assert len(d.promos) == 1
    assert d.promos[0]["name"] == "Shop Flowers Flyer"
    assert "NZ$123.49" in d.description()

def test_future_price_unknown(data):
    s,o,_ = data
    o.update(isVirtual=True, totalCost=0)
    d=normalize(s,o,selection={"recipes":[{"recipeName":"Dinner", "quantity":1}]*5})
    assert d.price is None and d.promos is None
    assert d.title == "5 meals for 4 people"

def test_confirmed_free_delivery(data):
    data[2]['total']=0
    assert normalize(*data).price == 0

def test_no_promo_and_paid_extras(data):
    data[2]['extras']=[{'productName':'Bread','price':4}]
    data[2]['products']=[]
    assert normalize(*data).promos == []

def test_skipped(data):
    data[1]['isSkipped']=True
    assert normalize(*data) is None

def test_cancelled(data):
    data[1]['orderStatus']={'styleTreatment':'Cancelled'}
    assert normalize(*data) is None

def test_missing_date(data):
    data[1]['deliveryDate']={}
    assert normalize(*data) is None

def test_dst(data):
    data[1]['deliveryDate']['actualDeliveryDate']='2026-10-03T00:00:00'
    assert normalize(*data).start.isoformat().endswith('+13:00')

def test_overnight(data):
    data[1]['deliveryDate'].update(actualDeliveryStartTime='22:00:00',actualDeliveryEndTime='02:00:00')
    d=normalize(*data)
    assert d.end.day == 13

def test_current_rollover(data):
    d=normalize(*data)
    assert current([d],timestamp('2026-09-12T23:59:00')) is d
    assert current([d],timestamp('2026-09-13T00:00:00')) is None

def test_no_invented_meal_count(data):
    d=normalize(data[0],data[1])
    assert d.title == 'Meal delivery for 4 people'

def test_no_private_address_in_attributes(data):
    data[1]['deliveryAddress']={'street':'SECRET'}
    assert 'SECRET' not in str(normalize(*data).attributes())


def test_meal_order_quantity_and_subscription_limit(data):
    selection = {'recipes': [
        {'recipeName': 'Third', 'timeStamp': 30},
        {'recipeName': 'First', 'timeStamp': 10, 'quantity': 2},
        {'recipeName': 'Fourth', 'timeStamp': 30},
        {'recipeName': 'Undated'},
        {'recipeName': 'Extra'},
        {'recipeName': 'Unselected', 'timeStamp': 1, 'quantity': 0},
    ]}
    d = normalize(*data, selection=selection)
    assert d.meal_names == ['First', 'First', 'Third', 'Fourth', 'Undated']
    assert selection['recipes'][0]['recipeName'] == 'Third'


def test_missing_recipe_preserves_day(data):
    d = normalize(*data, selection={'recipes': [
        {'timeStamp': 1}, {'recipeName': 'Second', 'timeStamp': 2}]})
    assert d.meal_names == [None, 'Second']
