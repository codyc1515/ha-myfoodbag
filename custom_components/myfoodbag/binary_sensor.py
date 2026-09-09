"""Complimentary items."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import BagEntity, discover


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry, async_add_entities, lambda c, e, b: [
        DeliveryBinary(c, e, b, "promo_items", "Promotional items")])


class DeliveryBinary(BagEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, bag, key, name):
        super().__init__(coordinator, entry, bag, key, name)
        self.key = key

    @property
    def is_on(self):
        d = self.delivery
        if d is None:
            return None
        return bool(d.promos) if d.promos is not None else None
