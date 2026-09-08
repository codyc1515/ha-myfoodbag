"""Shared bag entities and dynamic discovery."""
import hashlib
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .models import current


class BagEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, bag, key, name):
        super().__init__(coordinator)
        self.bag = bag
        identifier = entry.entry_id + "_" + hashlib.sha256(bag.encode()).hexdigest()[:16]
        self._attr_unique_id = identifier + "_" + key
        self._attr_name = name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, identifier)}, name=bag,
                                           manufacturer="My Food Bag", model="Meal deliveries")

    @property
    def delivery(self):
        return current(self.coordinator.data.get(self.bag, []))

    @property
    def extra_state_attributes(self):
        return self.delivery.attributes() if self.delivery else {}


def discover(entry, async_add_entities, factory):
    coordinator = entry.runtime_data
    known = set()

    @callback
    def add_bags():
        new = set(coordinator.data) - known
        known.update(new)
        async_add_entities([entity for bag in sorted(new) for entity in factory(coordinator, entry, bag)])

    add_bags()
    entry.async_on_unload(coordinator.async_add_listener(add_bags))
