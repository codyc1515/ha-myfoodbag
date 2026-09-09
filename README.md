# My Food Bag for Home Assistant

See your upcoming My Food Bag deliveries, meals, and tracking details in Home Assistant. Information refreshes every 30 minutes.

This is an unofficial integration. It lets you view your deliveries; use My Food Bag to change meals or manage orders.

## Installation

1. Extract the ZIP and copy the `myfoodbag` folder from `custom_components` into your Home Assistant `/config/custom_components/` folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **My Food Bag**.
4. Sign in with your My Food Bag email and password.
5. Open **Calendar** and select your bag type, such as **Fresh Start**, to see your deliveries.

## What you can see

Each bag type has its own calendar and delivery details, which you can add to your dashboards.

| Feature | What it shows |
|---|---|
| Delivery calendar | When your bag arrives, with entries such as **5 meals for 4 people** |
| Meals | Individual all-day recipe entries, starting on delivery day, when available |
| Delivery window | The scheduled start and end times |
| Tracking | Your courier tracking number and link |
| Price | The confirmed delivery total in NZD |
| Meal changes deadline | When you need to finish choosing your meals |
| Promotions | Free extras |

Tracking number, delivery price, and promotional items appear in the device's **Diagnostic** section.

## How deliveries are shown

Your dashboard details show the next delivery, keeping today's delivery visible until midnight in New Zealand. The calendar shows all available deliveries, including those that are still being planned. Skipped and cancelled deliveries are hidden.

Some details, such as prices, meals, and tracking, may only become available closer to delivery day. Home Assistant shows **Unknown** when information is missing. Future deliveries may change as My Food Bag confirms them.

Meals are ordered by their selection timestamps and shown on consecutive days, with delivery day as day one. A Saturday delivery with five meals shows meals from Saturday through Wednesday, without a specific meal time. Repeated recipe quantities occupy consecutive days. Tied timestamps keep the API order; recipes without timestamps follow the dated recipes. The delivery window remains a separate timed entry.

Delivery times follow New Zealand time, including daylight saving. Home Assistant may display them in your chosen local timezone.

## Sign-in and privacy

Use your My Food Bag email and password. If Home Assistant asks you to sign in again, follow the prompt to reconnect.

Your login details are saved in Home Assistant, so keep your configuration and backups secure. Delivery addresses and payment account details are not shown.

## Compatibility and help

Tested with Home Assistant **2026.9.1**.

If My Food Bag is temporarily unavailable, delivery information will return after a successful refresh. Changes to My Food Bag's service may require an integration update.
