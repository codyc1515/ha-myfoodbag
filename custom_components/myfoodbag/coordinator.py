"""Poll subscriptions and their delivery details."""
import asyncio
from datetime import timedelta
import logging
from urllib.parse import quote
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ApiError, AuthError
from .models import bag_name, normalize

_LOGGER = logging.getLogger(__name__)


class Coordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, _LOGGER, name="My Food Bag", config_entry=entry,
                         update_interval=timedelta(minutes=30))
        self.client = client

    async def _async_update_data(self):
        try:
            subscriptions = await self.client.get("/subscriptions/orders")
            if not isinstance(subscriptions, list):
                raise ApiError("Unexpected subscriptions response")
            result = {}
            seen = set()
            for subscription in subscriptions:
                bag = bag_name(subscription)
                deliveries = result.setdefault(bag, [])
                for order in subscription.get("orders", []):
                    basic = normalize(subscription, order)
                    if basic is None or basic.key in seen:
                        continue
                    seen.add(basic.key)
                    delivery_id = order.get("deliveryId")
                    summary = tracking = selection = None
                    if delivery_id:
                        delivery_id = quote(str(delivery_id), safe="")
                        summary = await self.client.get("/customer/delivery/summary/bydelivery/" + delivery_id, optional=True)
                        tracking = await self.client.get("/delivery/tracking/" + delivery_id, optional=True)
                    number = subscription.get("subscriptionNumber")
                    week = order.get("deliveryWeek")
                    if number and week:
                        params = {"promoId": order.get("promoId") or 0}
                        if delivery_id:
                            params["deliveryId"] = delivery_id
                        selection = await self.client.get(
                            f"/subscriptions/{quote(str(number), safe='')}/selection/{quote(str(week), safe='')}",
                            params=params, optional=True)
                    deliveries.append(normalize(subscription, order, summary, selection, tracking))
                deliveries.sort(key=lambda d: d.start)
            return result
        except AuthError as err:
            raise ConfigEntryAuthFailed("My Food Bag login must be renewed") from err
        except (ApiError, aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as err:
            raise UpdateFailed("Unable to retrieve My Food Bag deliveries") from err
