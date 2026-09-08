"""Delivery calendars, one per bag type."""
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.util import dt as dt_util
from .entity import BagEntity, discover


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry, async_add_entities, lambda c, e, b: [BagCalendar(c, e, b, "calendar", None)])


class BagCalendar(BagEntity, CalendarEntity):
    @staticmethod
    def make_event(delivery):
        return CalendarEvent(start=delivery.start, end=delivery.end,
                             summary=delivery.title, description=delivery.description())

    @property
    def event(self):
        now = dt_util.now()
        return next((self.make_event(d) for d in self.coordinator.data.get(self.bag, []) if d.end > now), None)

    async def async_get_events(self, hass, start_date, end_date):
        return [self.make_event(d) for d in self.coordinator.data.get(self.bag, [])
                if d.end > start_date and d.start < end_date]
