"""Delivery and all-day meal calendars, one per bag type."""
from datetime import timedelta
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

    def calendar_events(self):
        events = []
        for delivery in self.coordinator.data.get(self.bag, []):
            events.append(self.make_event(delivery))
            for offset, name in enumerate(delivery.meal_names):
                if not name:
                    continue
                day = delivery.start.date() + timedelta(days=offset)
                events.append(CalendarEvent(
                    start=day, end=day + timedelta(days=1), summary=name,
                    description=f"{delivery.bag}\nDay {offset + 1}\n"
                                f"Delivery: {delivery.start.date().isoformat()}",
                ))
        return sorted(events, key=lambda event: event.start_datetime_local)

    @property
    def event(self):
        now = dt_util.now()
        return next((event for event in self.calendar_events()
                     if event.end_datetime_local > now), None)

    async def async_get_events(self, hass, start_date, end_date):
        return [event for event in self.calendar_events()
                if event.end_datetime_local > start_date
                and event.start_datetime_local < end_date]
