"""Current delivery facts."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .entity import BagEntity, discover

SENSORS = (
    ("tracking_number", "NZ Post tracking number", None, None),
    ("window_start", "Delivery window start", SensorDeviceClass.TIMESTAMP, None),
    ("price", "Delivery price", SensorDeviceClass.MONETARY, "NZD"),
    ("deadline", "Meal changes deadline", SensorDeviceClass.TIMESTAMP, None),
)


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry, async_add_entities, lambda c, e, b: [DeliverySensor(c, e, b, *s) for s in SENSORS])


class DeliverySensor(BagEntity, SensorEntity):
    def __init__(self, coordinator, entry, bag, key, name, device_class, unit):
        super().__init__(coordinator, entry, bag, key, name)
        self.key = key
        if key in {"tracking_number", "price"}:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if unit:
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        d = self.delivery
        if d is None:
            return None
        if self.key == "tracking_number":
            return d.tracking.get("trackingNumber") or None
        if self.key == "window_start":
            return d.start
        return getattr(d, self.key)
